'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { uploadAsset, DuplicateFileError } from '@/hooks/useAssets';
import { apiClient, assetsApi } from '@/lib/api';
import {
  BrandAsset,
  getPipelineStatusConfig,
  getFileTypeIcon,
  formatFileSize,
  getFileTypeFromMime,
} from '@/types/assets';
import { AllFilesModal } from '@/components/ui/AllFilesModal';

interface UploadingFile {
  id: string;
  file: File;
  progress: number;
  status: 'uploading' | 'success' | 'error';
  error?: string;
}

interface AssetsResponse {
  count: number;
  showing: number;
  has_more: boolean;
  results: BrandAsset[];
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
  'text/plain',
];

const MAX_SIZE_MB = 50;
const LIMIT_OPTIONS = [3, 6, 9] as const;
const POLLING_INTERVAL = 5000;

interface DuplicateConfirmation {
  file: File;
  fileType: string;
  existingAsset: DuplicateFileError['existingAsset'];
}

export function FileUploadManager({ canEdit = true }: { canEdit?: boolean }) {
  const [assets, setAssets] = useState<BrandAsset[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [displayLimit, setDisplayLimit] = useState<typeof LIMIT_OPTIONS[number]>(6);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [showAllFiles, setShowAllFiles] = useState(false);
  const [duplicateConfirm, setDuplicateConfirm] = useState<DuplicateConfirmation | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Function to fetch assets with limit
  const fetchAssets = useCallback(async () => {
    try {
      const response = await apiClient.get(`/assets/?limit=${displayLimit}`);
      if (response.ok) {
        const data: AssetsResponse = await response.json();
        setAssets(data.results || []);
        setTotalCount(data.count || 0);
        setHasMore(data.has_more || false);
      }
    } catch (err) {
      console.error('Failed to load files:', err);
      setError('Failed to load files');
    } finally {
      setLoading(false);
    }
  }, [displayLimit]);

  // Check if any files are still processing (not indexed or failed)
  const hasPendingAssets = assets.some(
    (f) => f.pipeline_status !== 'indexed' && f.pipeline_status !== 'failed'
  );

  // Load existing uploaded files on mount and set up polling
  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  // Set up polling when there are pending files
  useEffect(() => {
    if (hasPendingAssets) {
      pollingRef.current = setInterval(() => {
        fetchAssets();
      }, POLLING_INTERVAL);
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [hasPendingAssets, fetchAssets]);

  const refresh = useCallback(() => {
    fetchAssets();
  }, [fetchAssets]);

  const retryPipeline = useCallback(async (assetId: number) => {
    try {
      await apiClient.post(`/assets/${assetId}/retry_pipeline/`, {});
      await fetchAssets();
    } catch (err) {
      console.error('Failed to retry pipeline:', err);
    }
  }, [fetchAssets]);

  const deleteAsset = useCallback(async (assetId: number): Promise<boolean> => {
    try {
      const response = await apiClient.delete(`/assets/${assetId}/`);
      if (response.ok) {
        await fetchAssets();
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to delete asset:', err);
      return false;
    }
  }, [fetchAssets]);

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
          // Use name-based check — instanceof can fail across module boundaries in Next.js
          const isDuplicate =
            err instanceof DuplicateFileError ||
            (err instanceof Error && err.name === 'DuplicateFileError' && 'existingAsset' in err);

          if (isDuplicate) {
            const dupErr = err as DuplicateFileError;
            // Show duplicate confirmation dialog
            setDuplicateConfirm({
              file: upload.file,
              fileType: getFileTypeFromMime(upload.file.type),
              existingAsset: dupErr.existingAsset,
            });
            // Remove from uploading list (handled by dialog now)
            setUploadingFiles((prev) => prev.filter((u) => u.id !== upload.id));
          } else {
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

  const handleDuplicateReplace = useCallback(async () => {
    if (!duplicateConfirm) return;
    const { file, fileType } = duplicateConfirm;
    setDuplicateConfirm(null);

    try {
      await uploadAsset(file, fileType, true); // replaceExisting = true
      await refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Replace failed';
      setError(msg);
    }
  }, [duplicateConfirm, refresh]);

  const handleDuplicateSkip = useCallback(() => {
    setDuplicateConfirm(null);
  }, []);

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
      {canEdit ? (
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
          accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,application/pdf,.doc,.docx,.txt"
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
      ) : (
        <div className="border-2 border-dashed border-white/10 rounded-lg p-6 text-center bg-white/5">
          <p className="text-sm text-brand-silver/50">
            You need editor access to upload files. Contact your workspace admin to upgrade your role.
          </p>
        </div>
      )}

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
      {assets.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-3">
              <h3 className="font-medium text-white">
                Your Files
                <span className="ml-2 text-sm text-brand-silver/70">
                  ({assets.length}{hasMore ? `/${totalCount}` : ''})
                </span>
              </h3>
              {hasPendingAssets && (
                <span className="text-xs text-brand-silver/70 animate-pulse">
                  🔄 Processing...
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {/* Limit selector */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-brand-silver/70">Show:</span>
                <select
                  value={displayLimit}
                  onChange={(e) => setDisplayLimit(Number(e.target.value) as typeof LIMIT_OPTIONS[number])}
                  className="px-2 py-1 text-xs rounded border border-white/20 bg-brand-dark text-white focus:outline-none focus:border-brand-electric"
                >
                  {LIMIT_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>
              {/* View All button */}
              {totalCount > displayLimit && (
                <button
                  onClick={() => setShowAllFiles(true)}
                  className="px-3 py-1 text-xs rounded border border-brand-electric/50 bg-brand-electric/20 text-brand-electric hover:bg-brand-electric/30 transition-colors"
                >
                  View All ({totalCount})
                </button>
              )}
            </div>
          </div>
          <ul className="divide-y divide-white/10 border border-white/10 rounded-lg bg-white/5">
            {assets.map((asset) => (
              <AssetRow key={asset.id} asset={asset} onRetry={handleRetry} onDelete={deleteAsset} canEdit={canEdit} />
            ))}
          </ul>
        </div>
      )}

      {loading && assets.length === 0 && (
        <div className="text-center py-8">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
          <p className="mt-2 text-sm text-brand-silver/70">Loading assets...</p>
        </div>
      )}

      {!loading && assets.length === 0 && (
        <div className="text-center py-8 text-brand-silver/50">
          <p>No files uploaded yet.</p>
          <p className="text-sm mt-1">Upload your first brand asset to get started.</p>
        </div>
      )}

      {/* All Files Modal */}
      <AllFilesModal
        isOpen={showAllFiles}
        onClose={() => {
          setShowAllFiles(false);
          refresh(); // Refresh the list when modal closes
        }}
        onDelete={async (fileId) => {
          await deleteAsset(Number(fileId));
        }}
      />

      {/* Duplicate File Confirmation Dialog */}
      {duplicateConfirm && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
          role="dialog"
          aria-modal="true"
          aria-labelledby="duplicate-dialog-title"
          onKeyDown={(e) => { if (e.key === 'Escape') handleDuplicateSkip(); }}
        >
          <div className="bg-brand-dark border border-white/20 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 id="duplicate-dialog-title" className="text-lg font-semibold text-white mb-2">
              File Already Exists
            </h3>
            <p className="text-brand-silver/80 text-sm mb-4">
              A file named <span className="font-medium text-white">&quot;{duplicateConfirm.existingAsset.file_name}&quot;</span> already exists
              (uploaded {new Date(duplicateConfirm.existingAsset.uploaded_at).toLocaleDateString()},
              status: {duplicateConfirm.existingAsset.pipeline_status}).
            </p>
            <p className="text-brand-silver/80 text-sm mb-6">
              Do you want to replace it with the new file?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={handleDuplicateSkip}
                className="px-4 py-2 text-sm rounded border border-white/20 text-brand-silver hover:bg-white/10 transition-colors"
              >
                Keep Existing
              </button>
              <button
                onClick={handleDuplicateReplace}
                className="px-4 py-2 text-sm rounded bg-brand-electric text-white hover:bg-brand-electric/80 transition-colors"
              >
                Replace File
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface AssetRowProps {
  asset: BrandAsset;
  onRetry: (assetId: number) => Promise<void>;
  onDelete: (assetId: number) => Promise<boolean>;
  canEdit?: boolean;
}

function AssetRow({ asset, onRetry, onDelete, canEdit = true }: AssetRowProps) {
  const [retrying, setRetrying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loadingUrl, setLoadingUrl] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  const handleView = async () => {
    setLoadingUrl(true);
    setError(null);
    try {
      const signedUrls = await assetsApi.getSignedUrl(asset.id.toString());
      window.open(signedUrls.view_url, '_blank');
    } catch (err) {
      setError('Failed to get file URL');
      console.error('Error getting signed URL:', err);
    } finally {
      setLoadingUrl(false);
    }
  };

  const handleDownload = async () => {
    setLoadingUrl(true);
    setError(null);
    try {
      const signedUrls = await assetsApi.getSignedUrl(asset.id.toString());
      const link = document.createElement('a');
      link.href = signedUrls.download_url;
      link.download = asset.file_name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setError('Failed to download file');
      console.error('Error downloading file:', err);
    } finally {
      setLoadingUrl(false);
    }
  };

  return (
    <li className="px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <span className="text-lg">{getFileTypeIcon(asset.file_type)}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{asset.file_name}</p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-brand-silver/70">{formatFileSize(asset.file_size)}</span>
            {error && <span className="text-xs text-red-400">{error}</span>}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span
          className={`text-xs px-2 py-1 rounded ${statusConfig.bgColor} ${statusConfig.color}`}
        >
          {statusConfig.icon} {statusConfig.label}
        </span>

        <span className="text-xs bg-brand-electric/20 text-brand-electric px-2 py-1 rounded">
          {asset.file_type}
        </span>

        {/* View button - show for indexed/curated files */}
        {(asset.pipeline_status === 'indexed' || asset.pipeline_status === 'curated') && (
          <button
            onClick={handleView}
            disabled={loadingUrl}
            className="text-brand-electric hover:text-brand-electric/80 disabled:opacity-50 transition-colors"
            title="View file"
          >
            {loadingUrl ? '⏳' : '👁️'}
          </button>
        )}

        {/* Download button - show for indexed/curated files */}
        {(asset.pipeline_status === 'indexed' || asset.pipeline_status === 'curated') && (
          <button
            onClick={handleDownload}
            disabled={loadingUrl}
            className="text-brand-electric hover:text-brand-electric/80 disabled:opacity-50 transition-colors"
            title="Download file"
          >
            ⬇️
          </button>
        )}

        {asset.pipeline_status === 'failed' && canEdit && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="text-xs text-brand-electric hover:text-brand-electric/80 disabled:opacity-50"
            title={asset.pipeline_error || 'Retry pipeline processing'}
          >
            {retrying ? '...' : '⟳ Retry'}
          </button>
        )}

        {canEdit && (
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-red-400 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          title="Delete file"
        >
          {deleting ? (
            <span className="inline-block animate-spin">⏳</span>
          ) : (
            <span>🗑️</span>
          )}
        </button>
        )}
      </div>
    </li>
  );
}
