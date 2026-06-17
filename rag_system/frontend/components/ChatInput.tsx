'use client';

import { useRef, useEffect, useState, KeyboardEvent, DragEvent, ChangeEvent } from 'react';

interface ImageAttachment {
  file: File;
  preview: string;
  ocrText?: string;
  isProcessing: boolean;
}

interface ChatInputProps {
  onSend: (text: string, images: ImageAttachment[]) => void;
  isLoading: boolean;
  apiUrl: string;
}

const EXAMPLE_QUERIES = [
  'Why was the project creation bug fixed after 3 months?',
  'What issues block #44132?',
  'Find duplicate bugs related to email notifications',
  'How did the permissions system evolve since 2010?',
];

export { type ImageAttachment };

export default function ChatInput({ onSend, isLoading, apiUrl }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const processImage = async (file: File): Promise<ImageAttachment> => {
    const preview = URL.createObjectURL(file);
    const attachment: ImageAttachment = { file, preview, isProcessing: true };

    // Upload to backend for OCR/VL processing
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await fetch(`${apiUrl}/ocr`, {
        method: 'POST',
        body: formData,
      });
      if (resp.ok) {
        const data = await resp.json();
        attachment.ocrText = data.text;
      }
    } catch (err) {
      console.error('OCR failed:', err);
    }
    attachment.isProcessing = false;
    return attachment;
  };

  const addFiles = async (files: FileList | File[]) => {
    const validFiles = Array.from(files).filter(f =>
      f.type.startsWith('image/') || f.type === 'application/pdf'
    );

    for (const file of validFiles) {
      // Add with processing state
      const tempPreview = URL.createObjectURL(file);
      const tempAttachment: ImageAttachment = {
        file,
        preview: tempPreview,
        isProcessing: true,
      };
      setImages(prev => [...prev, tempAttachment]);

      // Process OCR
      const processed = await processImage(file);
      setImages(prev =>
        prev.map(img => img.file === file ? processed : img)
      );
    }
  };

  const removeImage = (index: number) => {
    setImages(prev => {
      const newImages = [...prev];
      URL.revokeObjectURL(newImages[index].preview);
      newImages.splice(index, 1);
      return newImages;
    });
  };

  const handleSend = () => {
    if ((!text.trim() && images.length === 0) || isLoading) return;
    // Wait for all images to finish processing
    if (images.some(img => img.isProcessing)) return;
    onSend(text, images);
    setText('');
    setImages([]);
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
      e.target.value = ''; // Reset
    }
  };

  const handleExampleClick = (query: string) => {
    setText(query);
    textareaRef.current?.focus();
  };

  const canSend = (text.trim() || images.length > 0) && !isLoading && !images.some(img => img.isProcessing);

  return (
    <div
      className="chat-input-area"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="chat-input-container">
        {isDragOver && (
          <div className="drop-overlay">
            <div className="drop-overlay-text">📎 Drop images here for OCR</div>
          </div>
        )}

        {/* Image previews */}
        {images.length > 0 && (
          <div className="image-preview-strip">
            {images.map((img, i) => (
              <div key={i} className="image-preview-item">
                <img src={img.preview} alt={`Attachment ${i + 1}`} />
                {img.isProcessing && (
                  <div className="image-preview-processing">
                    <div className="image-preview-spinner" />
                  </div>
                )}
                {!img.isProcessing && (
                  <button
                    className="image-preview-remove"
                    onClick={() => removeImage(i)}
                    aria-label="Remove image"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Input wrapper */}
        <div className="chat-input-wrapper">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            id="chat-input"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about Redmine issues, upload images for analysis…"
            rows={1}
            disabled={isLoading}
          />

          <div className="chat-input-actions">
            {/* Upload button */}
            <button
              className="chat-action-btn upload-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
              title="Upload image or PDF for OCR"
              aria-label="Upload file"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,.pdf"
              multiple
              style={{ display: 'none' }}
              onChange={handleFileSelect}
            />

            {/* Send button */}
            <button
              className={`chat-send-btn ${isLoading ? 'loading' : ''}`}
              onClick={handleSend}
              disabled={!canSend}
              id="chat-send-btn"
              aria-label="Send message"
            >
              {isLoading ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round"/>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 19-7z" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </button>
          </div>
        </div>

        <div className="chat-input-hint">
          Ctrl+Enter to send · Drop images for OCR analysis
        </div>
      </div>
    </div>
  );
}

export { EXAMPLE_QUERIES };
