'use client';

import { useState, useCallback, useRef } from 'react';

/**
 * File upload response from Kong GCS direct upload
 */
interface GCSUploadResponse {
  name: string;
  bucket: string;
  generation: string;
  size: string;
  contentType: string;
  md5Hash: string;
  selfLink: string;
  mediaLink: string;
}

/**
 * Asset confirmation response from Django backend
 */
interface AssetConfirmationResponse {
  id: number;
  file_name: string;
  file_type: string;
  file_size: number;
  gcs_path: string;
  gcs_bucket: string;
  uploaded_at: string;
}

/**
 * Props for the KongFileUploader component
 */
interface KongFileUploaderProps {
  /** Company ID to associate the uploaded asset with */
  companyId?: number;
  /** Allowed file types (MIME types) */
  allowedTypes?: string[];
  /** Maximum file size in MB */
  maxSizeMB?: number;
  /** Callback when upload completes successfully */
  onUploadComplete?: (asset: AssetConfirmationResponse) => void;
  /** Callback when upload fails */
  onUploadError?: (error: string) => void;
  /** Optional CSS class name */
  className?: string;
  /** Upload button text */
  buttonText?: string;
  /** Whether to show file preview */
  showPreview?: boolean;
}

/**
 * Determines the file type category based on MIME type
 */
function getFileTypeCategory(mimeType: string): 'image' | 'video' | 'document' | 'other' {
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType.startsWith('video/')) return 'video';
  if (
    mimeType === 'application/pdf' ||
    mimeType.includes('document') ||
    mimeType.includes('text/')
  ) {
    return 'document';
  }
  return 'other';
}

/**
 * KongFileUploader - Direct GCS upload component using Kong Gateway
 * 
 * This component uploads files directly to Google Cloud Storage via Kong Gateway,
 * bypassing the Django backend for the actual file transfer. After the upload,
 * it calls the Django API to register the asset in the database.
 * 
 * Flow:
 * 1. User selects a file
 * 2. File is uploaded directly to GCS via Kong (POST /api/v1/storage/upload)
 * 3. Kong responds with GCS object metadata
 * 4. Frontend calls Django to confirm the upload (POST /api/v1/assets/confirm_gcs_upload/)
 * 5. Asset is now registered and trackable in the system
 */
export default function KongFileUploader({
  companyId,
  allowedTypes = [
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'video/mp4',
    'video/quicktime',
    'application/pdf',
  ],
  maxSizeMB = 50,
  onUploadComplete,
  onUploadError,
  className = '',
  buttonText = 'Upload File',
  showPreview = true,
}: KongFileUploaderProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Get the API base URL from environment
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  /**
   * Validates the selected file
   */
  const validateFile = useCallback(
    (file: File): string | null => {
      // Check file type
      if (!allowedTypes.includes(file.type)) {
        return `File type not allowed. Allowed types: ${allowedTypes.join(', ')}`;
      }

      // Check file size
      const maxBytes = maxSizeMB * 1024 * 1024;
      if (file.size > maxBytes) {
        return `File too large. Maximum size: ${maxSizeMB}MB`;
      }

      return null;
    },
    [allowedTypes, maxSizeMB]
  );

  /**
   * Handles file selection
   */
  const handleFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      // Clear previous state
      setError(null);
      setPreviewUrl(null);

      // Validate file
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        onUploadError?.(validationError);
        return;
      }

      setSelectedFile(file);

      // Create preview for images
      if (showPreview && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          setPreviewUrl(e.target?.result as string);
        };
        reader.readAsDataURL(file);
      }
    },
    [validateFile, showPreview, onUploadError]
  );

  /**
   * Uploads file directly to GCS via Kong Gateway
   */
  const uploadToGCS = async (file: File): Promise<GCSUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    // Kong GCS upload endpoint (handled by Kong, not Django)
    const response = await fetch(`${apiBaseUrl}/api/v1/storage/upload`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`GCS upload failed: ${errorText}`);
    }

    return response.json();
  };

  /**
   * Confirms the upload with Django backend to create asset record
   */
  const confirmUpload = async (
    file: File,
    gcsResponse: GCSUploadResponse
  ): Promise<AssetConfirmationResponse> => {
    const response = await fetch(`${apiBaseUrl}/api/v1/assets/confirm_gcs_upload/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({
        file_name: file.name,
        file_type: getFileTypeCategory(file.type),
        file_size: file.size,
        gcs_path: gcsResponse.name,
        gcs_bucket: gcsResponse.bucket,
        ...(companyId && { company_id: companyId }),
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to confirm upload');
    }

    return response.json();
  };

  /**
   * Handles the complete upload flow
   */
  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file first');
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setError(null);

    try {
      // Step 1: Upload to GCS via Kong
      setUploadProgress(30);
      const gcsResponse = await uploadToGCS(selectedFile);

      // Step 2: Confirm upload with Django
      setUploadProgress(80);
      const asset = await confirmUpload(selectedFile, gcsResponse);

      // Complete!
      setUploadProgress(100);
      onUploadComplete?.(asset);

      // Reset state
      setSelectedFile(null);
      setPreviewUrl(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMessage);
      onUploadError?.(errorMessage);
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  /**
   * Opens the file picker
   */
  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  /**
   * Clears the selected file
   */
  const handleClear = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className={`kong-file-uploader ${className}`}>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept={allowedTypes.join(',')}
        onChange={handleFileSelect}
        className="hidden"
        disabled={isUploading}
      />

      {/* Preview area */}
      {showPreview && previewUrl && (
        <div className="mb-4 relative">
          <img
            src={previewUrl}
            alt="Preview"
            className="max-w-full h-auto max-h-48 rounded-lg border border-gray-200"
          />
          <button
            onClick={handleClear}
            className="absolute top-2 right-2 bg-red-500 text-white rounded-full w-6 h-6 flex items-center justify-center hover:bg-red-600"
            disabled={isUploading}
          >
            ×
          </button>
        </div>
      )}

      {/* Selected file info */}
      {selectedFile && (
        <div className="mb-4 p-3 bg-gray-50 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">📁</span>
            <span className="text-sm font-medium truncate max-w-[200px]">
              {selectedFile.name}
            </span>
            <span className="text-xs text-gray-400">
              ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
            </span>
          </div>
          {!previewUrl && (
            <button
              onClick={handleClear}
              className="text-red-500 hover:text-red-600 text-sm"
              disabled={isUploading}
            >
              Remove
            </button>
          )}
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Progress bar */}
      {isUploading && (
        <div className="mb-4">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-1 text-center">
            {uploadProgress < 50 ? 'Uploading to GCS...' : 'Confirming upload...'}
          </p>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {!selectedFile ? (
          <button
            onClick={handleButtonClick}
            disabled={isUploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {buttonText}
          </button>
        ) : (
          <>
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isUploading ? 'Uploading...' : 'Upload to Cloud'}
            </button>
            <button
              onClick={handleButtonClick}
              disabled={isUploading}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Change File
            </button>
          </>
        )}
      </div>
    </div>
  );
}
