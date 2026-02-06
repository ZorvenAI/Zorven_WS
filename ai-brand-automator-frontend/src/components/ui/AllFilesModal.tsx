'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { Pagination } from '@/components/ui/Pagination';
import { FileFiltersBar } from '@/components/ui/FileFiltersBar';
import { getPipelineStatusConfig, PipelineStatus } from '@/types/assets';

interface AssetFile {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  pipeline_status: PipelineStatus;
  uploaded_at: string;
  gcs_path?: string;
}

interface AllFilesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDelete?: (fileId: string, fileName: string) => Promise<void>;
}

interface FilesResponse {
  count: number;
  total_pages: number;
  current_page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
  results: AssetFile[];
  filters_applied: {
    search: string | null;
    file_type: string | null;
    status: string | null;
    sort_by: string;
    sort_order: string;
  };
}

export function AllFilesModal({ isOpen, onClose, onDelete }: AllFilesModalProps) {
  const [files, setFiles] = useState<AssetFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<AssetFile | null>(null);
  const [signedUrls, setSignedUrls] = useState<{
    view_url: string;
    download_url: string;
    expires_at: string;
  } | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);

  // Filter state
  const [search, setSearch] = useState('');
  const [fileType, setFileType] = useState('');
  const [status, setStatus] = useState('');
  const [sortBy, setSortBy] = useState('uploaded_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        page_size: pageSize.toString(),
        sort_by: sortBy,
        sort_order: sortOrder,
      });

      if (search) params.set('search', search);
      if (fileType) params.set('file_type', fileType);
      if (status) params.set('status', status);

      const response = await apiClient.get(`/assets/?${params.toString()}`);
      if (response.ok) {
        const data: FilesResponse = await response.json();
        setFiles(data.results);
        setTotalPages(data.total_pages);
        setTotalCount(data.count);
        setHasNext(data.has_next);
        setHasPrevious(data.has_previous);
      } else {
        setError('Failed to load files');
      }
    } catch (err) {
      console.error('Error fetching files:', err);
      setError('An error occurred while loading files');
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize, search, fileType, status, sortBy, sortOrder]);

  useEffect(() => {
    if (isOpen) {
      fetchFiles();
    }
  }, [isOpen, fetchFiles]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [search, fileType, status, pageSize]);

  const handleDelete = async (file: AssetFile) => {
    if (!confirm(`Are you sure you want to delete "${file.file_name}"?`)) {
      return;
    }

    setDeletingId(file.id);
    setError('');

    try {
      if (onDelete) {
        await onDelete(file.id, file.file_name);
      } else {
        const response = await apiClient.delete(`/assets/${file.id}/`);
        if (!response.ok) {
          throw new Error('Failed to delete');
        }
      }
      // Refresh the list
      fetchFiles();
    } catch (err) {
      console.error('Error deleting file:', err);
      setError(`Failed to delete ${file.file_name}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleViewFile = async (file: AssetFile) => {
    setViewingFile(file);
    setSignedUrls(null);

    try {
      const response = await apiClient.get(`/assets/${file.id}/signed-url/`);
      if (response.ok) {
        const data = await response.json();
        setSignedUrls(data);
      } else {
        setError('Failed to get file URL');
      }
    } catch (err) {
      console.error('Error getting signed URL:', err);
      setError('Failed to get file URL');
    }
  };

  const closePreview = () => {
    setViewingFile(null);
    setSignedUrls(null);
  };

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
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-brand-dark border border-white/10 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h2 className="text-xl font-semibold text-white">All Files</h2>
          <button
            onClick={onClose}
            className="text-brand-silver/70 hover:text-white text-2xl leading-none"
          >
            ✕
          </button>
        </div>

        {/* Filters */}
        <div className="p-4 border-b border-white/10">
          <FileFiltersBar
            onSearchChange={setSearch}
            onFileTypeChange={setFileType}
            onStatusChange={setStatus}
            onSortChange={(sb, so) => {
              setSortBy(sb);
              setSortOrder(so);
            }}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mt-4 bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
            </div>
          ) : files.length === 0 ? (
            <div className="text-center py-12 text-brand-silver/70">
              No files found
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs text-brand-silver/70 border-b border-white/10">
                  <th className="pb-3 font-medium">Name</th>
                  <th className="pb-3 font-medium">Type</th>
                  <th className="pb-3 font-medium">Size</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Uploaded</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {files.map((file) => {
                  const statusConfig = getPipelineStatusConfig(file.pipeline_status || 'pending');
                  return (
                    <tr key={file.id} className="hover:bg-white/5">
                      <td className="py-3 pr-4">
                        <span className="text-sm text-white truncate max-w-[200px] block">
                          {file.file_name}
                        </span>
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
                      <td className="py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleViewFile(file)}
                            className="text-brand-electric hover:text-brand-electric/80 text-sm"
                            title="View file"
                          >
                            👁️
                          </button>
                          <button
                            onClick={() => handleDelete(file)}
                            disabled={deletingId === file.id}
                            className="text-red-400 hover:text-red-300 disabled:opacity-50 text-sm"
                            title="Delete file"
                          >
                            {deletingId === file.id ? '⏳' : '🗑️'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {!loading && files.length > 0 && (
          <div className="p-4 border-t border-white/10">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              hasNext={hasNext}
              hasPrevious={hasPrevious}
              onPageChange={setCurrentPage}
              pageSize={pageSize}
              onPageSizeChange={setPageSize}
              totalCount={totalCount}
            />
          </div>
        )}
      </div>

      {/* File Preview Modal */}
      {viewingFile && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/80" onClick={closePreview}>
          <div
            className="bg-brand-dark border border-white/10 rounded-xl shadow-2xl w-full max-w-2xl p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white truncate flex-1">
                {viewingFile.file_name}
              </h3>
              <button onClick={closePreview} className="text-brand-silver/70 hover:text-white ml-4">
                ✕
              </button>
            </div>

            {!signedUrls ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-brand-electric"></div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Preview based on file type */}
                {viewingFile.file_type === 'image' && (
                  <div className="rounded-lg overflow-hidden bg-white/5 flex items-center justify-center">
                    <img
                      src={signedUrls.view_url}
                      alt={viewingFile.file_name}
                      className="max-h-[400px] max-w-full object-contain"
                    />
                  </div>
                )}

                {viewingFile.file_type === 'video' && (
                  <div className="rounded-lg overflow-hidden bg-white/5">
                    <video
                      src={signedUrls.view_url}
                      controls
                      className="max-h-[400px] w-full"
                    />
                  </div>
                )}

                {viewingFile.file_type === 'document' && (
                  <div className="rounded-lg overflow-hidden bg-white/5 p-8 text-center">
                    <p className="text-brand-silver/70 mb-4">
                      Document preview not available in browser
                    </p>
                  </div>
                )}

                {/* Download button */}
                <div className="flex justify-center gap-4 pt-4">
                  <a
                    href={signedUrls.view_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2 text-sm rounded-lg border border-white/20 bg-white/5 text-white hover:bg-white/10 transition-colors"
                  >
                    Open in New Tab
                  </a>
                  <a
                    href={signedUrls.download_url}
                    download={viewingFile.file_name}
                    className="px-4 py-2 text-sm rounded-lg bg-brand-electric text-white hover:bg-brand-electric/90 transition-colors"
                  >
                    Download
                  </a>
                </div>

                <p className="text-xs text-brand-silver/50 text-center">
                  Links expire at {new Date(signedUrls.expires_at).toLocaleTimeString()}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
