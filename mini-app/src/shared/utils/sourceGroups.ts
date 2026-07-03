export type SourceAwareItem = {
  id: number;
  source_type?: string | null;
  source_group_id?: string | null;
  source_look_title?: string | null;
  source_look_image_url?: string | null;
};

export type SourceItemSection<T extends SourceAwareItem> = {
  kind: 'item';
  key: string;
  item: T;
};

export type LookSourceSection<T extends SourceAwareItem> = {
  kind: 'look';
  key: string;
  sourceGroupId: string;
  title: string;
  imageUrl: string | null;
  items: T[];
};

export type SourceSection<T extends SourceAwareItem> =
  | SourceItemSection<T>
  | LookSourceSection<T>;

export function groupLookSourcedItems<T extends SourceAwareItem>(items: T[]): SourceSection<T>[] {
  const sections: SourceSection<T>[] = [];
  const groups = new Map<string, LookSourceSection<T>>();

  for (const item of items) {
    const sourceGroupId = item.source_group_id?.trim();
    if (item.source_type === 'LOOK' && sourceGroupId) {
      let group = groups.get(sourceGroupId);
      if (!group) {
        group = {
          kind: 'look',
          key: `look-${sourceGroupId}`,
          sourceGroupId,
          title: item.source_look_title?.trim() || 'Образ',
          imageUrl: item.source_look_image_url ?? null,
          items: [],
        };
        groups.set(sourceGroupId, group);
        sections.push(group);
      }
      group.items.push(item);
      if (!group.imageUrl && item.source_look_image_url) {
        group.imageUrl = item.source_look_image_url;
      }
      continue;
    }

    sections.push({ kind: 'item', key: `item-${item.id}`, item });
  }

  return sections;
}
