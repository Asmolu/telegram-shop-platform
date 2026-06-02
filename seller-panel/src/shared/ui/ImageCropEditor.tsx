import { useEffect, useMemo, useRef, useState } from 'react';

export interface ImageCropSpec {
  id: string;
  title: string;
  aspectLabel: string;
  aspectRatio: number;
  outputWidth: number;
  outputHeight: number;
  minWidth: number;
  minHeight: number;
}

export const PRODUCT_IMAGE_CROP_SPEC: ImageCropSpec = {
  id: 'product',
  title: 'Product image crop',
  aspectLabel: '4:5',
  aspectRatio: 4 / 5,
  outputWidth: 1200,
  outputHeight: 1500,
  minWidth: 600,
  minHeight: 750,
};

export const NATIVE_BANNER_CROP_SPEC: ImageCropSpec = {
  id: 'native-banner',
  title: 'Native banner crop',
  aspectLabel: '16:9',
  aspectRatio: 16 / 9,
  outputWidth: 1600,
  outputHeight: 900,
  minWidth: 800,
  minHeight: 450,
};

export const AGGRESSIVE_BANNER_CROP_SPEC: ImageCropSpec = {
  id: 'aggressive-banner',
  title: 'Promotional banner crop',
  aspectLabel: '3:1',
  aspectRatio: 3 / 1,
  outputWidth: 1800,
  outputHeight: 600,
  minWidth: 900,
  minHeight: 300,
};

interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface LoadedImage {
  image: HTMLImageElement;
  width: number;
  height: number;
}

interface ImageCropEditorProps {
  file: File;
  spec: ImageCropSpec;
  onApply: (file: File) => void;
  onCancel: () => void;
}

export function ImageCropEditor({ file, spec, onApply, onCancel }: ImageCropEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [loadedImage, setLoadedImage] = useState<LoadedImage | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      setLoadedImage({
        image,
        width: image.naturalWidth,
        height: image.naturalHeight,
      });
      setZoom(1);
      setOffsetX(0);
      setOffsetY(0);
      setError(null);
    };
    image.onerror = () => setError('Could not read selected image.');
    image.src = objectUrl;

    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  const cropRect = useMemo(() => {
    if (!loadedImage) {
      return null;
    }
    return getCropRect(loadedImage.width, loadedImage.height, spec.aspectRatio, zoom, offsetX, offsetY);
  }, [loadedImage, offsetX, offsetY, spec.aspectRatio, zoom]);

  useEffect(() => {
    if (!loadedImage || !cropRect || !canvasRef.current) {
      return;
    }

    drawCropPreview(canvasRef.current, loadedImage.image, cropRect, spec);
  }, [cropRect, loadedImage, spec]);

  const isTooSmall = Boolean(
    loadedImage && (loadedImage.width < spec.minWidth || loadedImage.height < spec.minHeight),
  );

  async function handleApply() {
    if (!loadedImage || !cropRect || isTooSmall) {
      setError(
        `Минимальный размер изображения: ${spec.minWidth}x${spec.minHeight}`,
      );
      return;
    }

    setProcessing(true);
    setError(null);
    try {
      const outputCanvas = document.createElement('canvas');
      drawCropPreview(outputCanvas, loadedImage.image, cropRect, spec);
      const { blob, mimeType } = await exportCanvas(outputCanvas, getPreferredMimeType(file.type));
      const croppedFile = new File([blob], getOutputFilename(file.name, spec.id, mimeType), {
        type: mimeType,
        lastModified: Date.now(),
      });
      onApply(croppedFile);
    } catch {
      setError('Could not crop image.');
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="crop-modal" role="dialog" aria-modal="true" aria-labelledby="crop-editor-title">
      <div className="crop-modal__surface">
        <div className="section-heading">
          <div>
            <h2 id="crop-editor-title">{spec.title}</h2>
            <p className="image-hints">
              Рекомендуемый размер: {spec.outputWidth}x{spec.outputHeight}. Минимальный размер:{' '}
              {spec.minWidth}x{spec.minHeight}. Соотношение: {spec.aspectLabel}.
            </p>
          </div>
          <button className="text-button" type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>

        <div className="crop-preview-frame">
          {loadedImage ? (
            <canvas className="crop-preview" ref={canvasRef} />
          ) : (
            <div className="crop-preview crop-preview-loading">Loading image...</div>
          )}
        </div>

        {loadedImage ? (
          <p className={isTooSmall ? 'form-error' : 'image-hints'}>
            Source image: {loadedImage.width}x{loadedImage.height}
          </p>
        ) : null}
        {error ? <div className="form-error">{error}</div> : null}

        <div className="crop-controls">
          <label className="field">
            <span>Zoom</span>
            <input
              max="4"
              min="1"
              step="0.01"
              type="range"
              value={zoom}
              onChange={(event) => setZoom(Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>Horizontal crop</span>
            <input
              max="100"
              min="-100"
              step="1"
              type="range"
              value={offsetX}
              onChange={(event) => setOffsetX(Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>Vertical crop</span>
            <input
              max="100"
              min="-100"
              step="1"
              type="range"
              value={offsetY}
              onChange={(event) => setOffsetY(Number(event.target.value))}
            />
          </label>
        </div>

        <div className="form-actions">
          <button className="button button-secondary" type="button" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="button button-primary"
            disabled={!loadedImage || isTooSmall || processing}
            type="button"
            onClick={() => void handleApply()}
          >
            {processing ? 'Applying...' : 'Apply crop'}
          </button>
        </div>
      </div>
    </div>
  );
}

function getCropRect(
  imageWidth: number,
  imageHeight: number,
  aspectRatio: number,
  zoom: number,
  offsetX: number,
  offsetY: number,
): CropRect {
  let width = imageWidth;
  let height = width / aspectRatio;

  if (height > imageHeight) {
    height = imageHeight;
    width = height * aspectRatio;
  }

  width /= zoom;
  height /= zoom;

  const maxCenterXOffset = Math.max(0, (imageWidth - width) / 2);
  const maxCenterYOffset = Math.max(0, (imageHeight - height) / 2);
  const centerX = imageWidth / 2 + (offsetX / 100) * maxCenterXOffset;
  const centerY = imageHeight / 2 + (offsetY / 100) * maxCenterYOffset;

  return {
    x: clamp(centerX - width / 2, 0, imageWidth - width),
    y: clamp(centerY - height / 2, 0, imageHeight - height),
    width,
    height,
  };
}

function drawCropPreview(
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  cropRect: CropRect,
  spec: ImageCropSpec,
) {
  canvas.width = spec.outputWidth;
  canvas.height = spec.outputHeight;
  const context = canvas.getContext('2d');
  if (!context) {
    return;
  }

  context.clearRect(0, 0, spec.outputWidth, spec.outputHeight);
  context.drawImage(
    image,
    cropRect.x,
    cropRect.y,
    cropRect.width,
    cropRect.height,
    0,
    0,
    spec.outputWidth,
    spec.outputHeight,
  );
}

async function exportCanvas(canvas: HTMLCanvasElement, preferredMimeType: string) {
  const preferredBlob = await canvasToBlob(canvas, preferredMimeType);
  if (preferredBlob) {
    return { blob: preferredBlob, mimeType: preferredMimeType };
  }

  const fallbackBlob = await canvasToBlob(canvas, 'image/jpeg');
  if (!fallbackBlob) {
    throw new Error('Canvas export failed');
  }
  return { blob: fallbackBlob, mimeType: 'image/jpeg' };
}

function canvasToBlob(canvas: HTMLCanvasElement, mimeType: string) {
  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob((blob) => resolve(blob), mimeType, 0.92);
  });
}

function getPreferredMimeType(type: string) {
  if (type === 'image/png' || type === 'image/webp' || type === 'image/jpeg') {
    return type;
  }
  return 'image/jpeg';
}

function getOutputFilename(filename: string, specId: string, mimeType: string) {
  const extension = mimeType === 'image/png' ? 'png' : mimeType === 'image/webp' ? 'webp' : 'jpg';
  const basename = filename.replace(/\.[^.]+$/, '') || 'image';
  return `${basename}-${specId}.${extension}`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
