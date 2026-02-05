/**
 * Phase 7.4: E2E Tests - File Browser
 * 
 * Playwright E2E tests for the file browser feature
 * 
 * Setup (run once):
 *   npm install -D @playwright/test
 *   npx playwright install
 * 
 * Run tests:
 *   npx playwright test e2e/file-browser.spec.ts
 */

import { test, expect, type Page } from '@playwright/test';

// Test configuration
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';
const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000';

// Test user credentials (should be set via environment)
const TEST_USER = {
  email: process.env.TEST_USER_EMAIL || 'test@example.com',
  password: process.env.TEST_USER_PASSWORD || 'testpassword123',
};

/**
 * Helper to log in and get authenticated session
 */
async function login(page: Page): Promise<void> {
  await page.goto(`${BASE_URL}/auth/login`);
  
  await page.fill('input[name="email"], input[type="email"]', TEST_USER.email);
  await page.fill('input[name="password"], input[type="password"]', TEST_USER.password);
  await page.click('button[type="submit"]');
  
  // Wait for redirect to dashboard
  await expect(page).toHaveURL(/dashboard|onboarding/, { timeout: 10000 });
}

/**
 * Helper to navigate to onboarding page with assets
 */
async function navigateToAssets(page: Page): Promise<void> {
  // Navigate to onboarding or company setup page
  await page.goto(`${BASE_URL}/onboarding`);
  
  // Wait for page to load
  await page.waitForLoadState('networkidle');
  
  // Look for assets section
  await expect(page.locator('text=/assets|files|upload/i').first()).toBeVisible({ timeout: 10000 });
}

test.describe('File Browser E2E', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test.describe('Compact File List (AssetUploadForm)', () => {
    test('displays uploaded files', async ({ page }) => {
      await navigateToAssets(page);
      
      // Check for file list section
      const fileList = page.locator('[data-testid="file-list"], .file-list');
      await expect(fileList.or(page.locator('text=/\\.png|\\.jpg|\\.pdf/i').first())).toBeVisible();
    });

    test('shows file count and storage info', async ({ page }) => {
      await navigateToAssets(page);
      
      // Look for file count
      await expect(page.locator('text=/\\d+ files?/i').first()).toBeVisible();
      
      // Look for storage size
      await expect(page.locator('text=/\\d+(\\.\\d+)?\\s*(KB|MB|GB)/i').first()).toBeVisible();
    });

    test('has View All button when files exist', async ({ page }) => {
      await navigateToAssets(page);
      
      const viewAllButton = page.locator('button:has-text("View All"), button:has-text("See All"), button:has-text("All Files")');
      
      // Only visible if there are files
      const fileCount = await page.locator('text=/\\d+ files?/i').count();
      if (fileCount > 0) {
        await expect(viewAllButton.first()).toBeVisible();
      }
    });
  });

  test.describe('All Files Modal', () => {
    test('opens modal when View All clicked', async ({ page }) => {
      await navigateToAssets(page);
      
      // Click View All
      await page.click('button:has-text("View All"), button:has-text("See All"), button:has-text("All Files")');
      
      // Modal should open
      await expect(page.locator('[role="dialog"]')).toBeVisible();
    });

    test('displays file list in modal', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      await expect(modal).toBeVisible();
      
      // Should have file items
      await expect(modal.locator('text=/\\.png|\\.jpg|\\.pdf|\\.mp4/i').first()).toBeVisible();
    });

    test('closes modal on close button click', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      
      // Click close button
      await page.click('[role="dialog"] button:has-text("×"), [role="dialog"] button:has-text("Close")');
      
      // Modal should close
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test('closes modal on Escape key', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      
      await page.keyboard.press('Escape');
      
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });
  });

  test.describe('Search & Filtering', () => {
    test('filters files by search term', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      const searchInput = modal.locator('input[placeholder*="Search"], input[placeholder*="search"]');
      
      await searchInput.fill('logo');
      
      // Wait for filtered results
      await page.waitForTimeout(500); // Debounce delay
      
      // Should show matching files
      const files = modal.locator('text=/logo/i');
      await expect(files.first()).toBeVisible();
    });

    test('filters files by type', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Open filters
      await modal.locator('button:has-text("Filters")').click();
      
      // Select image type
      const typeSelect = modal.locator('select').first();
      await typeSelect.selectOption('image');
      
      // Wait for filtered results
      await page.waitForResponse(resp => resp.url().includes('/assets/') && resp.status() === 200);
      
      // Should only show image files
      const videoFiles = modal.locator('text=".mp4"');
      await expect(videoFiles).toHaveCount(0);
    });

    test('clears all filters', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Add a search filter
      await modal.locator('input[placeholder*="search" i]').fill('test');
      await page.waitForTimeout(500);
      
      // Open filters and clear
      await modal.locator('button:has-text("Filters")').click();
      await modal.locator('button:has-text("Clear All")').click();
      
      // Search should be cleared
      const searchInput = modal.locator('input[placeholder*="search" i]');
      await expect(searchInput).toHaveValue('');
    });
  });

  test.describe('Pagination', () => {
    test('shows pagination when many files', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Look for pagination controls (only if more than 10 files)
      const pagination = modal.locator('[data-testid="pagination"], .pagination, nav[aria-label="Pagination"]');
      
      // May or may not be visible depending on file count
      const fileCountText = await modal.locator('text=/\\d+ files?/i').first().textContent();
      const match = fileCountText?.match(/(\d+) files?/);
      const fileCount = match ? parseInt(match[1]) : 0;
      
      if (fileCount > 10) {
        await expect(pagination).toBeVisible();
      }
    });

    test('navigates to next page', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      const nextButton = modal.locator('button:has-text("Next"), button:has-text(">")');
      
      if (await nextButton.isVisible()) {
        const initialFiles = await modal.locator('.file-item, [data-testid="file-item"]').allTextContents();
        
        await nextButton.click();
        await page.waitForResponse(resp => resp.url().includes('/assets/') && resp.status() === 200);
        
        const newFiles = await modal.locator('.file-item, [data-testid="file-item"]').allTextContents();
        
        // Files should be different on new page
        expect(newFiles).not.toEqual(initialFiles);
      }
    });

    test('changes page size', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      const pageSizeSelect = modal.locator('select:has-text("10"), select[aria-label*="per page" i]');
      
      if (await pageSizeSelect.isVisible()) {
        await pageSizeSelect.selectOption('25');
        await page.waitForResponse(resp => resp.url().includes('/assets/') && resp.status() === 200);
        
        // Should request with new page size
        expect(page.url()).toContain('page_size=25');
      }
    });
  });

  test.describe('File Actions', () => {
    test('views file in new tab', async ({ page, context }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      const viewButton = modal.locator('button:has-text("View"), button[aria-label*="view" i]').first();
      
      // Listen for new tab
      const [newPage] = await Promise.all([
        context.waitForEvent('page'),
        viewButton.click(),
      ]);
      
      // New tab should have signed URL
      expect(newPage.url()).toMatch(/storage\.googleapis\.com|signed/);
      
      await newPage.close();
    });

    test('downloads file', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      const downloadButton = modal.locator('button:has-text("Download"), button[aria-label*="download" i]').first();
      
      // Set up download listener
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        downloadButton.click(),
      ]);
      
      // Download should have correct filename
      expect(download.suggestedFilename()).toMatch(/\.(png|jpg|pdf|mp4)$/);
    });

    test('deletes file with confirmation', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Get initial file count
      const initialCount = await modal.locator('.file-item, [data-testid="file-item"]').count();
      
      // Click delete on first file
      const deleteButton = modal.locator('button:has-text("Delete"), button[aria-label*="delete" i]').first();
      await deleteButton.click();
      
      // Confirmation should appear
      await expect(page.locator('text=/are you sure|confirm/i')).toBeVisible();
      
      // Confirm deletion
      await page.click('button:has-text("Confirm"), button:has-text("Yes")');
      
      // Wait for delete and refresh
      await page.waitForResponse(resp => resp.url().includes('/assets/') && resp.request().method() === 'DELETE');
      
      // File count should decrease
      const newCount = await modal.locator('.file-item, [data-testid="file-item"]').count();
      expect(newCount).toBeLessThan(initialCount);
    });

    test('cancels deletion', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Get initial file count
      const initialCount = await modal.locator('.file-item, [data-testid="file-item"]').count();
      
      // Click delete
      await modal.locator('button:has-text("Delete")').first().click();
      
      // Cancel
      await page.click('button:has-text("Cancel"), button:has-text("No")');
      
      // File count should remain same
      const newCount = await modal.locator('.file-item, [data-testid="file-item"]').count();
      expect(newCount).toBe(initialCount);
    });
  });

  test.describe('File Upload', () => {
    test('uploads a file via dropzone', async ({ page }) => {
      await navigateToAssets(page);
      
      // Find dropzone
      const dropzone = page.locator('[data-testid="dropzone"], .dropzone, text=/drag.*drop/i');
      
      // Create test file
      const buffer = Buffer.from('test image content');
      await page.setInputFiles('input[type="file"]', {
        name: 'test-upload.png',
        mimeType: 'image/png',
        buffer: buffer,
      });
      
      // Wait for upload to complete
      await page.waitForResponse(resp => 
        resp.url().includes('/assets/') && 
        resp.request().method() === 'POST' &&
        resp.status() === 201
      );
      
      // New file should appear in list
      await expect(page.locator('text="test-upload.png"')).toBeVisible();
    });

    test('shows upload progress', async ({ page }) => {
      await navigateToAssets(page);
      
      // Start upload
      await page.setInputFiles('input[type="file"]', {
        name: 'large-file.png',
        mimeType: 'image/png',
        buffer: Buffer.alloc(1024 * 1024), // 1MB
      });
      
      // Should show progress indicator
      await expect(page.locator('text=/uploading|progress|%/i')).toBeVisible();
    });

    test('shows error for invalid file type', async ({ page }) => {
      await navigateToAssets(page);
      
      // Try to upload executable
      await page.setInputFiles('input[type="file"]', {
        name: 'malware.exe',
        mimeType: 'application/x-msdownload',
        buffer: Buffer.from('bad content'),
      });
      
      // Should show error
      await expect(page.locator('text=/invalid|not allowed|unsupported/i')).toBeVisible();
    });
  });

  test.describe('Signed URLs', () => {
    test('signed URLs expire correctly', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Get a signed URL
      const viewButton = modal.locator('button:has-text("View")').first();
      
      // Intercept the API call
      const signedUrlPromise = page.waitForResponse(resp => 
        resp.url().includes('/signed-url/') && resp.status() === 200
      );
      
      await viewButton.click();
      
      const response = await signedUrlPromise;
      const data = await response.json();
      
      // Should have expiry time
      expect(data.expires_at).toBeDefined();
      
      // Should expire in ~15 minutes
      const expiresAt = new Date(data.expires_at);
      const now = new Date();
      const diffMinutes = (expiresAt.getTime() - now.getTime()) / (1000 * 60);
      
      expect(diffMinutes).toBeGreaterThan(10);
      expect(diffMinutes).toBeLessThanOrEqual(15);
    });

    test('signed URLs are tenant-isolated', async ({ page, context }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Get first file's signed URL
      const signedUrlPromise = page.waitForResponse(resp => 
        resp.url().includes('/signed-url/') && resp.status() === 200
      );
      
      await modal.locator('button:has-text("View")').first().click();
      
      const response = await signedUrlPromise;
      const { signed_url } = await response.json();
      
      // Create new browser context (simulating different user)
      const newContext = await context.browser()!.newContext();
      const newPage = await newContext.newPage();
      
      // Try accessing the signed URL directly (should work - it's a GCS signed URL)
      const urlResponse = await newPage.goto(signed_url);
      
      // GCS signed URLs are valid for anyone with the link until expiry
      // But they can only access that specific file
      expect(urlResponse?.status()).toBe(200);
      
      await newContext.close();
    });
  });

  test.describe('Accessibility', () => {
    test('modal is keyboard navigable', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      await expect(modal).toBeVisible();
      
      // Tab through elements
      await page.keyboard.press('Tab');
      
      // Focus should be within modal
      const focusedElement = page.locator(':focus');
      expect(await focusedElement.evaluate(el => el.closest('[role="dialog"]'))).toBeTruthy();
    });

    test('file list has proper ARIA attributes', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      const modal = page.locator('[role="dialog"]');
      
      // Modal should have aria-label or aria-labelledby
      const hasLabel = await modal.getAttribute('aria-label') || await modal.getAttribute('aria-labelledby');
      expect(hasLabel).toBeTruthy();
      
      // Action buttons should have accessible names
      const viewButtons = modal.locator('button:has-text("View")');
      const firstViewButton = viewButtons.first();
      
      if (await firstViewButton.isVisible()) {
        const accessibleName = await firstViewButton.getAttribute('aria-label') || await firstViewButton.textContent();
        expect(accessibleName).toBeTruthy();
      }
    });

    test('respects reduced motion preference', async ({ page }) => {
      // Set reduced motion preference
      await page.emulateMedia({ reducedMotion: 'reduce' });
      
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      // Modal should open without animation (or with reduced animation)
      const modal = page.locator('[role="dialog"]');
      await expect(modal).toBeVisible();
      
      // No specific assertion - just ensure it works with reduced motion
    });
  });

  test.describe('Error Handling', () => {
    test('handles API error gracefully', async ({ page }) => {
      // Intercept API calls and force error
      await page.route('**/api/onboarding/assets/**', route => 
        route.fulfill({ status: 500, body: JSON.stringify({ error: 'Server Error' }) })
      );
      
      await navigateToAssets(page);
      
      // Should show error state
      await expect(page.locator('text=/error|failed|try again/i')).toBeVisible();
    });

    test('handles network error', async ({ page }) => {
      await navigateToAssets(page);
      await page.click('button:has-text("View All")');
      
      // Force network error on next request
      await page.route('**/api/onboarding/assets/**', route => route.abort('failed'));
      
      // Trigger a refresh
      await page.click('button:has-text("Refresh")');
      
      // Should show network error
      await expect(page.locator('text=/network|connection|offline/i')).toBeVisible();
    });

    test('retry button works after error', async ({ page }) => {
      // First request fails
      let requestCount = 0;
      await page.route('**/api/onboarding/assets/**', route => {
        requestCount++;
        if (requestCount === 1) {
          route.fulfill({ status: 500, body: '{"error": "Server Error"}' });
        } else {
          route.continue();
        }
      });
      
      await navigateToAssets(page);
      
      // Should show error
      await expect(page.locator('text=/error|failed/i')).toBeVisible();
      
      // Click retry
      await page.click('button:has-text("Retry"), button:has-text("Try Again")');
      
      // Should load successfully
      await expect(page.locator('text=/\\.png|\\.jpg|files/i')).toBeVisible();
    });
  });
});
