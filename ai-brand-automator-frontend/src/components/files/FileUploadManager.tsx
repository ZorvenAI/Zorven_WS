'use client';

import { useState, useCallback, useRef } from 'react';
import { useAssets, uploadAsset } from '@/hooks/useAssets';
import {
  BrandAsset,
  getPipelineStatusConfig,
  getFileTypeIcon,
  formatFileSize,
  getFileTypeFromMime,
} from '@/types/assets';

interface UploadingFile {
  id: string;
  file: File;
  progress: number;
  status: 'uploading' | 'success' | 'error';
  error?: string;
}

const ALLOWED_TYPES = [
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
  'video/mp4',
  'video/quicktime',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

const MAX_SIZE_MB = 50;

export function FileUploadManager() {
  const { assets, loading, error, refresh, retryPipeline, deleteAsset, hasPendingAssets } = useAssets({
    pollingInterval: 5000, // Poll every 5 seconds for status updates
  });

  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback((file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return `File type not allowed: ${file.type}`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large. Maximum size is ${MAX_SIZE_MB}MB`;
    }
    return null;
  }, []);

  const handleUpload = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);

      // Create uploading entries
      const newUploads: UploadingFile[] = fileArray.map((file) => ({
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        file,
        progress: 0,
        status: 'uploading' as const,
      }));

      setUploadingFiles((prev) => [...prev, ...newUploads]);

      // Upload each file
      for (const upload of newUploads) {
        const validationError = validateFile(upload.file);

        if (validationError) {
          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? { ...u, status: 'error' as const, error: validationError }
                : u
            )
          );
          continue;
        }

        try {
          // Simulate progress updates
          setUploadingFiles((prev) =>
            prev.map((u) => (u.id === upload.id ? { ...u, progress: 30 } : u))
          );

          const fileType = getFileTypeFromMime(upload.file.type);
          await uploadAsset(upload.file, fileType);

          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id ? { ...u, progress: 100, status: 'success' as const } : u
            )
          );

          // Refresh assets list
          await refresh();

          // Remove successful upload from list after delay
          setTimeout(() => {
            setUploadingFiles((prev) => prev.filter((u) => u.id !== upload.id));
          }, 2000);
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : 'Upload failed';
          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? { ...u, status: 'error' as const, error: errorMessage }
                : u
            )
          );
        }
      }
    },
    [validateFile, refresh]
  );

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleUpload(e.dataTransfer.files);
      }
    },
    [handleUpload]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        handleUpload(e.target.files);
        // Reset input
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [handleUpload]
  );

  const handleRetry = useCallback(
    async (assetId: number) => {
      await retryPipeline(assetId);
    },
    [retryPipeline]
  );

  const removeFailedUpload = useCallback((uploadId: string) => {
    setUploadingFiles((prev) => prev.filter((u) => u.id !== uploadId));
  }, []);

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive
            ? 'border-brand-electric bg-brand-electric/10'
            : 'border-white/20 bg-white/5 hover:bg-white/10 hover:border-brand-electric/50'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          multiple
          accept={ALLOWED_TYPES.join(',')}
          onChange={handleFileSelect}
        />

        <div className="space-y-4">
          <div className="text-brand-silver/70">
            <svg
              className="mx-auto h-12 w-12 text-brand-electric/60"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="font-medium text-brand-electric hover:text-brand-electric/80"
            >
              Click to upload
            </button>
            <span className="text-brand-silver/70"> or drag and drop</span>
          </div>
          <p className="text-xs text-brand-silver/50">
            Images, PDFs, Videos up to {MAX_SIZE_MB}MB each
          </p>
        </div>
      </div>

      {/* Uploading Files */}
      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-medium text-white">Uploading</h3>
          <div className="space-y-2">
            {uploadingFiles.map((upload) => (
              <div
                key={upload.id}
                className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/10"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <span className="text-lg">
                    {getFileTypeIcon(getFileTypeFromMime(upload.file.type))}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">
                      {upload.file.name}
                    </p>
                    <p className="text-xs text-brand-silver/70">
                      {formatFileSize(upload.file.size)}
                    </p>
                  </div>
                </div>

                {upload.status === 'uploading' && (
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-electric transition-all duration-300"
                        style={{ width: `${upload.progress}%` }}
                      />
                    </div>
                    <span className="text-xs text-brand-silver/70 w-8">
                      {upload.progress}%
                    </span>
                  </div>
                )}

                {upload.status === 'success' && (
                  <span className="text-green-400 text-sm">✓ Uploaded</span>
                )}

                {upload.status === 'error' && (
                  <div className="flex items-center gap-2">
                    <span className="text-red-400 text-xs">{upload.error}</span>
                    <button
                      onClick={() => removeFailedUpload(upload.id)}
                      className="text-brand-silver/50 hover:text-white"
                    >
                      ✕
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Assets List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-white">Your Files</h3>
          <div className="flex items-center gap-2">
            {hasPendingAssets && (
              <span className="text-xs text-brand-silver/70 animate-pulse">
                🔄 Processing...
              </span>
            )}
            <button
              onClick={refresh}
              className="text-sm text-brand-electric hover:text-brand-electric/80"
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && assets.length === 0 ? (
          <div className="text-center py-8">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
            <p className="mt-2 text-sm text-brand-silver/70">Loading assets...</p>
          </div>
        ) : assets.length === 0 ? (
          <div className="text-center py-8 text-brand-silver/50">
            <p>No files uploaded yet.</p>
            <p className="text-sm mt-1">Upload your first brand asset to get started.</p>
          </div>
        ) : (
          <div className="divide-y divide-white/10 border border-white/10 rounded-lg bg-white/5">
            {assets.map((asset) => (
              <AssetRow key={asset.id} asset={asset} onRetry={handleRetry} onDelete={deleteAsset} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface AssetRowProps {
  asset: BrandAsset;
  onRetry: (assetId: number) => Promise<void>;
  onDelete: (assetId: number) => Promise<boolean>;
}

function AssetRow({ asset, onRetry, onDelete }: AssetRowProps) {
  const [retrying, setRetrying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const statusConfig = getPipelineStatusConfig(asset.pipeline_status);

  const handleRetry = async () => {
    setRetrying(true);
    await onRetry(asset.id);
    setRetrying(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete "${asset.file_name}"?`)) {
      return;
    }
    setDeleting(true);
    await onDelete(asset.id);
    setDeleting(false);
  };

  return (
    <div className="px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <span className="text-lg">{getFileTypeIcon(asset.file_type)}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{asset.file_name}</p>
          <p className="text-xs text-brand-silver/70">{formatFileSize(asset.file_size)}</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span
          className={`text-xs px-2 py-1 rounded ${statusConfig.bgColor} ${statusConfig.color}`}
        >
          {statusConfig.icon} {statusConfig.label}
        </span>

        {asset.pipeline_status === 'failed' && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="text-xs text-brand-electric hover:text-brand-electric/80 disabled:opacity-50"
            title={asset.pipeline_error || 'Retry pipeline processing'}
          >
            {retrying ? '...' : '⟳ Retry'}
          </button>
        )}

        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
          title="Delete file"
        >
          {deleting ? '...' : '🗑️'}
        </button>
      </div>
    </div>
  );
}
