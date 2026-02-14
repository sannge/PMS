/**
 * File Upload Component
 *
 * Drag-and-drop file upload with progress indicator.
 *
 * Features:
 * - Drag and drop file upload
 * - Click to browse files
 * - Progress indicator for uploads
 * - Multiple file support
 * - File type filtering
 * - Max file size validation
 * - Upload status feedback
 */

import { useState, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/file-utils";
import {
  Upload,
  X,
  File,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import {
  useUploadFile,
  useUploadProgress,
  type EntityType,
  type UploadProgress,
} from "@/hooks/use-attachments";

// ============================================================================
// Types
// ============================================================================

export interface FileUploadProps {
  /**
   * Entity type to attach files to
   */
  entityType?: EntityType;
  /**
   * Entity ID to attach files to
   */
  entityId?: string;
  /**
   * Accept specific file types (e.g., "image/*,.pdf")
   */
  accept?: string;
  /**
   * Allow multiple file selection
   */
  multiple?: boolean;
  /**
   * Maximum file size in bytes (default: 100MB)
   */
  maxSize?: number;
  /**
   * Callback when file is uploaded successfully
   */
  onUploadComplete?: (attachment: { id: string; file_name: string }) => void;
  /**
   * Callback when upload fails
   */
  onUploadError?: (error: string) => void;
  /**
   * Optional className
   */
  className?: string;
  /**
   * Compact mode for inline usage
   */
  compact?: boolean;
  /**
   * Disabled state
   */
  disabled?: boolean;
}

// ============================================================================
// Constants
// ============================================================================

const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB default

// ============================================================================
// Sub-Components
// ============================================================================

interface UploadItemProps {
  upload: UploadProgress;
  onRemove: () => void;
}

function UploadItem({ upload, onRemove }: UploadItemProps): JSX.Element {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-card p-3">
      {/* Icon */}
      <div className="flex-shrink-0">
        {upload.status === "uploading" ? (
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
        ) : upload.status === "complete" ? (
          <CheckCircle2 className="h-5 w-5 text-green-500" />
        ) : upload.status === "error" ? (
          <AlertCircle className="h-5 w-5 text-destructive" />
        ) : (
          <File className="h-5 w-5 text-muted-foreground" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">
          {upload.fileName}
        </p>
        {upload.status === "uploading" && (
          <div className="mt-1">
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${upload.progress}%` }}
              />
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {upload.progress}% uploaded
            </p>
          </div>
        )}
        {upload.status === "error" && (
          <p className="mt-0.5 text-xs text-destructive">
            {upload.error || "Upload failed"}
          </p>
        )}
        {upload.status === "complete" && (
          <p className="mt-0.5 text-xs text-green-600">Upload complete</p>
        )}
      </div>

      {/* Remove button */}
      {(upload.status === "complete" || upload.status === "error") && (
        <button
          onClick={onRemove}
          className="flex-shrink-0 rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function FileUpload({
  entityType,
  entityId,
  accept,
  multiple = true,
  maxSize = MAX_FILE_SIZE,
  onUploadComplete,
  onUploadError,
  className,
  compact = false,
  disabled = false,
}: FileUploadProps): JSX.Element {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // TanStack Query hooks
  const uploadMutation = useUploadFile();
  const {
    uploads,
    addUpload,
    updateProgress,
    completeUpload,
    failUpload,
    removeUpload,
  } = useUploadProgress();

  // Handle file selection
  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0 || disabled) return;

      const fileArray = Array.from(files);

      for (const file of fileArray) {
        // Validate file size
        if (file.size > maxSize) {
          onUploadError?.(
            `File "${file.name}" exceeds maximum size of ${formatFileSize(maxSize)}`,
          );
          continue;
        }

        // Generate unique ID for this upload
        const uploadId = `upload-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

        // Add to progress tracking
        addUpload(uploadId, file.name);

        try {
          // Upload file with progress callback
          const attachment = await uploadMutation.mutateAsync({
            file,
            entityType,
            entityId,
            onProgress: (progress: any) => updateProgress(uploadId, progress),
          });

          completeUpload(uploadId);
          onUploadComplete?.({
            id: attachment.id,
            file_name: attachment.file_name,
          });
        } catch (error) {
          const errorMessage =
            error instanceof Error ? error.message : "Upload failed";
          failUpload(uploadId, errorMessage);
          onUploadError?.(`Failed to upload "${file.name}": ${errorMessage}`);
        }
      }
    },
    [
      disabled,
      maxSize,
      entityType,
      entityId,
      uploadMutation,
      addUpload,
      updateProgress,
      completeUpload,
      failUpload,
      onUploadComplete,
      onUploadError,
    ],
  );

  // Handle drag events
  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) {
        setIsDragOver(true);
      }
    },
    [disabled],
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      if (!disabled) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [disabled, handleFiles],
  );

  // Handle click to browse
  const handleClick = useCallback(() => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [disabled]);

  // Handle input change
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      handleFiles(e.target.files);
      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    },
    [handleFiles],
  );

  // Get pending uploads
  const pendingUploads = uploads.filter(
    (u) => u.status === "uploading" || u.status === "pending",
  );
  const completedOrErrorUploads = uploads.filter(
    (u) => u.status === "complete" || u.status === "error",
  );

  // Remove a completed/error upload from list
  const handleRemoveUpload = useCallback(
    (uploadId: string) => {
      removeUpload(uploadId);
    },
    [removeUpload],
  );

  if (compact) {
    return (
      <div className={className}>
        <button
          type="button"
          onClick={handleClick}
          disabled={disabled}
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm",
            "border border-dashed border-border bg-background",
            "text-muted-foreground hover:text-foreground hover:border-primary/50",
            "transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          <Upload className="h-4 w-4" />
          <span>Attach file</span>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleInputChange}
          className="hidden"
        />
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        className={cn(
          "relative rounded-lg border-2 border-dashed p-6 transition-colors",
          "cursor-pointer hover:border-primary/50",
          isDragOver && "border-primary bg-primary/5",
          disabled && "cursor-not-allowed opacity-50",
          !isDragOver && !disabled && "border-border hover:bg-accent/50",
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleInputChange}
          className="hidden"
          disabled={disabled}
        />

        <div className="flex flex-col items-center justify-center text-center">
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-full",
              isDragOver
                ? "bg-primary/10 text-primary"
                : "bg-muted text-muted-foreground",
            )}
          >
            <Upload className="h-6 w-6" />
          </div>

          <div className="mt-4">
            <p className="text-sm font-medium text-foreground">
              {isDragOver
                ? "Drop files here"
                : "Drop files here or click to browse"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {accept ? `Accepts: ${accept}` : "Any file type"} &bull; Max{" "}
              {formatFileSize(maxSize)}
            </p>
          </div>
        </div>
      </div>

      {/* Upload Progress List */}
      {(pendingUploads.length > 0 || completedOrErrorUploads.length > 0) && (
        <div className="space-y-2">
          {pendingUploads.map((upload) => (
            <UploadItem
              key={upload.fileId}
              upload={upload}
              onRemove={() => handleRemoveUpload(upload.fileId)}
            />
          ))}
          {completedOrErrorUploads.map((upload) => (
            <UploadItem
              key={upload.fileId}
              upload={upload}
              onRemove={() => handleRemoveUpload(upload.fileId)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default FileUpload;
