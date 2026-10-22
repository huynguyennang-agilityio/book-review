// Dữ liệu và hàm thuần cho màn duyệt nhân vật (interrupt `review_characters`).

export interface CharacterCandidate {
  slug: string;
  name: string;
  // Đường dẫn tương đối trong thư mục media, tải qua `/projects/{id}/media`.
  images: string[];
  reused: boolean;
  regenLeft: number;
}

export interface CharacterReview {
  characters: CharacterCandidate[];
  picks: Record<string, number>;
  spentUsd: number;
}

export function parseCharacters(raw: Record<string, unknown>): CharacterReview {
  const chars = (raw.characters ?? {}) as Record<
    string,
    { name?: string; images?: string[]; reused?: boolean; regen_left?: number }
  >;
  const cost = (raw.cost ?? {}) as { usd?: number };
  return {
    characters: Object.entries(chars).map(([slug, c]) => ({
      slug,
      name: c.name ?? slug,
      images: c.images ?? [],
      reused: Boolean(c.reused),
      regenLeft: c.regen_left ?? 0,
    })),
    picks: (raw.picks ?? {}) as Record<string, number>,
    spentUsd: typeof cost.usd === "number" ? cost.usd : 0,
  };
}

// Có thể duyệt khi mọi nhân vật mới đều đã chọn 1 ảnh (nhân vật tái dùng từ series tự chọn).
export function canApprove(
  chars: CharacterCandidate[],
  picks: Record<string, number>,
  regen: Record<string, string>,
): boolean {
  return (
    Object.keys(regen).length === 0 &&
    chars.every((c) => c.reused || (picks[c.slug] != null && picks[c.slug] < c.images.length))
  );
}

export interface CharacterDecision {
  selections: Record<string, number>;
  regenerate?: Record<string, string>;
}
