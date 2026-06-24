export const RECEIPT_MAX_SIDE_PX = 1800;
export const RECEIPT_IMAGE_QUALITY = 0.88;

export type PreparedReceiptImage = {
  file: File;
  optimized: boolean;
};

const ACCEPTED_RECEIPT_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

export async function prepareReceiptImage(file: File): Promise<PreparedReceiptImage> {
  if (!ACCEPTED_RECEIPT_TYPES.has(file.type)) {
    return { file, optimized: false };
  }

  const source = await decodeImage(file);
  if (!source) {
    return { file, optimized: false };
  }

  const scale = Math.min(1, RECEIPT_MAX_SIDE_PX / Math.max(source.width, source.height));
  if (scale >= 1) {
    source.close?.();
    return { file, optimized: false };
  }

  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  const context = canvas.getContext('2d');
  if (!context) {
    source.close?.();
    return { file, optimized: false };
  }

  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source.image, 0, 0, canvas.width, canvas.height);
  source.close?.();

  const blob = await canvasToBlob(canvas, 'image/jpeg', RECEIPT_IMAGE_QUALITY);
  if (!blob) {
    return { file, optimized: false };
  }

  if (blob.size >= file.size && file.size > 0) {
    return { file, optimized: false };
  }

  return {
    file: new File([blob], replaceImageExtension(file.name, 'jpg'), {
      type: 'image/jpeg',
      lastModified: file.lastModified,
    }),
    optimized: true,
  };
}

type DecodedImage = {
  image: CanvasImageSource;
  width: number;
  height: number;
  close?: () => void;
};

async function decodeImage(file: File): Promise<DecodedImage | null> {
  if ('createImageBitmap' in window) {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' } as ImageBitmapOptions);
      return {
        image: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        close: () => bitmap.close(),
      };
    } catch {
      // Fall through to HTMLImageElement decoding.
    }
  }

  if (typeof URL === 'undefined' || typeof Image === 'undefined') {
    return null;
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await loadHtmlImage(objectUrl);
    return {
      image,
      width: image.naturalWidth,
      height: image.naturalHeight,
    };
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function loadHtmlImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Could not decode receipt image'));
    image.src = src;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number) {
  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality);
  });
}

function replaceImageExtension(name: string, extension: string) {
  const cleanName = name.trim() || 'receipt';
  return cleanName.replace(/\.[a-z0-9]+$/i, '') + `.${extension}`;
}
