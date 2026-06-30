export type ProductEditorMode = 'create' | 'edit';

export function applyGeneratedProductSlug({
  mode,
  currentSlug,
  generatedSlug,
  wasManuallyEdited,
}: {
  mode: ProductEditorMode;
  currentSlug: string;
  generatedSlug: string | null | undefined;
  wasManuallyEdited: boolean;
}) {
  const nextSlug = generatedSlug?.trim() ?? '';
  if (mode !== 'create' || wasManuallyEdited || currentSlug.trim() || !nextSlug) {
    return currentSlug;
  }

  return nextSlug;
}
