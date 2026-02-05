'use client';

import { AssetFile, assetsApi, SignedUrlResponse } from '@/lib/api';
import { getPipelineStatusConfig } from '@/types/assets';
import { useState } from 'react';

interface FileListItemProps {
  file: AssetFile;
  onDelete?: (file: AssetFile) => Promise<void>;
  onView?: (file: AssetFile, signedUrls: SignedUrlResponse) => void;
  showActions?: boolean;
  compact?: boolean;
}

export function FileListItem({
  file,
  onDelete,
  onView,
  showActions = true,
  compact = false,
}: FileListItemProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [isLoadingUrl, setIsLoadingUrl] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const statusConfig = getPipelineStatusConfig(file.pipeline_status || 'pending');

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const handleView = async () => {
    setIsLoadingUrl(true);
    setError(null);

    try {
      const signedUrls = await assetsApi.getSignedUrl(file.id);
      if (onView) {
        onView(file, signedUrls);
      } else {
        // Default behavior: open in new tab
        window.open(signedUrls.view_url, '_blank');
      }
    } catch (err) {
      setError('Failed to get file URL');
      console.error('Error getting signed URL:', err);
    } finally {
      setIsLoadingUrl(false);
    }
  };

  const handleDownload = async () => {
    setIsLoadingUrl(true);
    setError(null);

    try {
      const signedUrls = await assetsApi.getSignedUrl(file.id);
      // Create a temporary link and click it to trigger download
      const link = document.createElement('a');
      link.href = signedUrls.download_url;
      link.download = file.file_name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setError('Failed to download file');
      console.error('Error downloading file:', err);
    } finally {
      setIsLoadingUrl(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete "${file.file_name}"?`)) {
      return;
    }

    setIsDeleting(true);
    setError(null);

    try {
      if (onDelete) {
        await onDelete(file);
      } else {
        await assetsApi.deleteAsset(file.id);
      }
    } catch (err) {
      setError('Failed to delete file');
      console.error('Error deleting file:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  const getFileIcon = (fileType: string) => {
    switch (fileType) {
      case 'image':
        return '🖼️';
      case 'video':
        return '🎬';
      case 'document':
        return '📄';
      default:
        return '📁';
    }
  };

  if (compact) {
    return (
      <div className="flex items-center justify-between px-3 py-2 hover:bg-white/5 rounded-lg transition-colors">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="text-lg">{getFileIcon(file.file_type)}</span>
          <span className="text-sm text-white truncate">{file.file_name}</span>
          <span className="text-xs text-brand-silver/50">
            ({formatFileSize(file.file_size)})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded ${statusConfig.bgColor} ${statusConfig.color}`}>
            {statusConfig.icon}
          </span>
          {showActions && (
            <div className="flex items-center gap-1">
              <button
                onClick={handleView}
                disabled={isLoadingUrl}
                className="p-1 text-brand-electric hover:text-brand-electric/80 disabled:opacity-50"
                title="View"
              >
                {isLoadingUrl ? '⏳' : '👁️'}
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="p-1 text-red-400 hover:text-red-300 disabled:opacity-50"
                title="Delete"
              >
                {isDeleting ? '⏳' : '🗑️'}
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <tr className="hover:bg-white/5 transition-colors">
      <td className="py-3 pr-4">
        <div className="flex items-center gap-2">
          <span className="text-lg">{getFileIcon(file.file_type)}</span>
          <span className="text-sm text-white truncate max-w-[200px]" title={file.file_name}>
            {file.file_name}
          </span>
        </div>
        {error && <span className="text-xs text-red-400 mt-1">{error}</span>}
      </td>
      <td className="py-3 pr-4">
        <span className="text-xs bg-brand-electric/20 text-brand-electric px-2 py-1 rounded">
          {file.file_type}
        </span>
      </td>
      <td className="py-3 pr-4 text-sm text-brand-silver/70">
        {formatFileSize(file.file_size)}
      </td>
      <td className="py-3 pr-4">
        <span className={`text-xs px-2 py-1 rounded ${statusConfig.bgColor} ${statusConfig.color}`}>
          {statusConfig.icon} {statusConfig.label}
        </span>
      </td>
      <td className="py-3 pr-4 text-xs text-brand-silver/70">
        {formatDate(file.uploaded_at)}
      </td>
      {showActions && (
        <td className="py-3 text-right">
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={handleView}
              disabled={isLoadingUrl}
              className="text-brand-electric hover:text-brand-electric/80 disabled:opacity-50 text-sm"
              title="View file"
            >
              {isLoadingUrl ? '⏳' : '👁️'}
            </button>
            <button
              onClick={handleDownload}
              disabled={isLoadingUrl}
              className="text-brand-electric hover:text-brand-electric/80 disabled:opacity-50 text-sm"
              title="Download file"
            >
              ⬇️
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="text-red-400 hover:text-red-300 disabled:opacity-50 text-sm"
              title="Delete file"
            >
              {isDeleting ? '⏳' : '🗑️'}
            </button>
          </div>
        </td>
      )}
    </tr>
  );
}
