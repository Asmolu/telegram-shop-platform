import { afterEach, describe, expect, it, vi } from 'vitest';
import { prepareReceiptImage, RECEIPT_MAX_SIDE_PX } from './receiptImage';

describe('prepareReceiptImage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('resizes oversized receipts to a readable JPEG blob', async () => {
    const source = new File([new Uint8Array(4000)], 'receipt.png', { type: 'image/png' });
    const close = vi.fn();
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({
      width: 3600,
      height: 2400,
      close,
    }));
    mockCanvas(new Blob([new Uint8Array(1000)], { type: 'image/jpeg' }));

    const prepared = await prepareReceiptImage(source);

    expect(prepared.optimized).toBe(true);
    expect(prepared.file.type).toBe('image/jpeg');
    expect(prepared.file.name).toBe('receipt.jpg');
    expect(prepared.file.size).toBe(1000);
    expect(close).toHaveBeenCalledTimes(1);
  });

  it('keeps small receipt files unchanged', async () => {
    const source = new File([new Uint8Array(1000)], 'receipt.webp', { type: 'image/webp' });
    const close = vi.fn();
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({
      width: RECEIPT_MAX_SIDE_PX - 1,
      height: 900,
      close,
    }));

    const prepared = await prepareReceiptImage(source);

    expect(prepared.optimized).toBe(false);
    expect(prepared.file).toBe(source);
    expect(close).toHaveBeenCalledTimes(1);
  });
});

function mockCanvas(blob: Blob) {
  const originalCreateElement = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation((tagName) => {
    if (tagName !== 'canvas') {
      return originalCreateElement(tagName);
    }
    return {
      width: 0,
      height: 0,
      getContext: () => ({
        fillStyle: '',
        fillRect: vi.fn(),
        drawImage: vi.fn(),
      }),
      toBlob: (callback: BlobCallback) => callback(blob),
    } as unknown as HTMLCanvasElement;
  });
}
