---
name: odoo-content-management
version: "1.0"
description: Website content and page management
target_agents:
  - odoo_worker
triggers:
  - "website"
  - "page"
  - "blog"
  - "SEO"
  - "CMS"
priority: 7
max_tokens: 400
---
# Website Content Management

## Page Builder
- Use the drag-and-drop website builder to create and edit pages without code
- Structure pages with building blocks: text, image, columns, cards, calls-to-action
- Apply consistent styling using the theme customizer for fonts, colors, and spacing
- Create reusable content snippets for repeated elements (testimonial blocks, feature grids)
- Preview pages on mobile and tablet viewports before publishing

## SEO Metadata
- Set a unique page title (under 60 characters) and meta description (150-160 characters) for every page
- Configure the URL slug to be short, descriptive, and keyword-relevant
- Add Open Graph and Twitter Card meta tags for rich social sharing previews
- Use structured data (JSON-LD) for product pages, blog posts, and FAQ sections
- Submit the sitemap.xml to Google Search Console after publishing new pages

## Blog Management
- Organize blog posts under topic-based blog categories (tags)
- Set post visibility: published, unpublished draft, or scheduled for future date
- Include a featured image and excerpt for blog listing page display
- Enable comments with moderation to encourage engagement while filtering spam
- Cross-link related blog posts to improve internal linking and session duration

## Menu Structure
- Define the header navigation menu with logical grouping and dropdown sub-menus
- Limit top-level menu items to 5-7 for usability and scannability
- Link menu items to internal pages, external URLs, or anchor sections
- Create a footer menu for secondary links: legal pages, sitemap, contact information
- Update menus whenever pages are added, renamed, or removed to prevent broken links
