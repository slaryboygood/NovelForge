/*
 * NovelForge V3 Default Artwork Manifest —— Visual Asset Contract 的唯一入口。
 *
 * 规则（Visual Asset Contract）：
 *   real story asset → product default artwork → semantic icon
 *
 * * 组件不允许自己保存图片路径，也不允许自己写随机 gradient；
 * * Story Assets 必须来自真实数据引用（不能用角色名 hardcode 图片）；
 * * 默认资源文件不存在时，这里保持 `url: undefined`，让 UI 自动进入
 *   semantic icon fallback —— 不引用不存在的文件，因此不会 build error；
 * * 真实资源就位后，只需在这里填 url（或改成 import），全产品同时生效。
 *
 * Product V3 Visual Asset Gate（2026-09-16）：6 个 required 默认资源已经就位并在此接入。
 * 这里仍然只做「解析」，不判断作品 / 角色 / 地点 / 势力是谁：
 * 谁是主角、哪张封面属于哪本小说，都不是这一层能猜的。
 */

// Product Default Artwork（正式产品默认资源；路径以 docs/V3_VISUAL_ASSET_REQUIREMENTS.json 为准）。
// 通过 import 交给打包器处理指纹与体积，组件层面依然只认 Manifest。
import defaultNovelCover from '../../assets/defaults/default_novel_cover.webp'
import defaultHeroBanner from '../../assets/defaults/default_hero_banner.webp'
import defaultCharacter from '../../assets/defaults/default_character.webp'
import defaultLocation from '../../assets/defaults/default_location.webp'
// 势力徽记需要真实透明通道：内容包给的是 PNG（requirements 允许 WebP or PNG）。
import defaultFaction from '../../assets/defaults/default_faction.png'
import defaultChapter from '../../assets/defaults/default_chapter.webp'

/** 实体视觉种类（与 EntityVisual 一一对应）。 */
export type ArtworkKind = 'novelCover' | 'hero' | 'character' | 'location'
  | 'faction' | 'chapter' | 'route'

/** 空态插画种类。 */
export type EmptyArtworkKind = 'characters' | 'world' | 'simulation' | 'outline'
  | 'review'

export interface ArtworkSlot {
  id: string
  kind: ArtworkKind | EmptyArtworkKind
  /** 真实资源就位后填这里（相对 ui/src/assets 的 import 或 public 路径）。 */
  url?: string
  /** 需求规格（同时写在 docs/V3_VISUAL_ASSET_REQUIREMENTS.json）。 */
  ratio: string
  size: string
  targetPath: string
}

export const DEFAULT_ARTWORK: Record<ArtworkKind, ArtworkSlot> = {
  novelCover: {
    id: 'default_novel_cover', kind: 'novelCover', url: defaultNovelCover,
    ratio: '2:3', size: '800×1200',
    targetPath: 'ui/src/assets/defaults/default_novel_cover.webp',
  },
  hero: {
    id: 'default_hero_banner', kind: 'hero', url: defaultHeroBanner,
    ratio: '16:9', size: '1600×900',
    targetPath: 'ui/src/assets/defaults/default_hero_banner.webp',
  },
  character: {
    id: 'default_character', kind: 'character', url: defaultCharacter,
    ratio: '4:5', size: '800×1000',
    targetPath: 'ui/src/assets/defaults/default_character.webp',
  },
  location: {
    id: 'default_location', kind: 'location', url: defaultLocation,
    ratio: '16:9', size: '1200×675',
    targetPath: 'ui/src/assets/defaults/default_location.webp',
  },
  faction: {
    id: 'default_faction', kind: 'faction', url: defaultFaction,
    ratio: '1:1', size: '512×512',
    targetPath: 'ui/src/assets/defaults/default_faction.png',
  },
  chapter: {
    id: 'default_chapter', kind: 'chapter', url: defaultChapter,
    ratio: '16:9', size: '960×540',
    targetPath: 'ui/src/assets/defaults/default_chapter.webp',
  },
  route: {
    id: 'default_route', kind: 'route', ratio: '16:9', size: '960×540',
    targetPath: 'ui/src/assets/defaults/default_route.webp',
  },
}

export const EMPTY_ARTWORK: Record<EmptyArtworkKind, ArtworkSlot> = {
  characters: {
    id: 'empty_characters', kind: 'characters', ratio: '4:3', size: '800×600',
    targetPath: 'ui/src/assets/empty-states/empty_characters.webp',
  },
  world: {
    id: 'empty_world', kind: 'world', ratio: '4:3', size: '800×600',
    targetPath: 'ui/src/assets/empty-states/empty_world.webp',
  },
  simulation: {
    id: 'empty_simulation', kind: 'simulation', ratio: '4:3', size: '800×600',
    targetPath: 'ui/src/assets/empty-states/empty_simulation.webp',
  },
  outline: {
    id: 'empty_outline', kind: 'outline', ratio: '4:3', size: '800×600',
    targetPath: 'ui/src/assets/empty-states/empty_outline.webp',
  },
  review: {
    id: 'empty_review', kind: 'review', ratio: '4:3', size: '800×600',
    targetPath: 'ui/src/assets/empty-states/empty_review.webp',
  },
}

export interface ResolvedArtwork {
  kind: ArtworkKind
  imageUrl: string
  /** 视觉来源：真实故事资源 / 产品默认资源 / 语义图标（最终 fallback）。 */
  source: 'story' | 'default' | 'icon'
}

/** 统一解析顺序：真实 story asset → product default → semantic icon。 */
export function resolveEntityArtwork(kind: ArtworkKind,
  storyUrl = ''): ResolvedArtwork {
  if (storyUrl) return { kind, imageUrl: storyUrl, source: 'story' }
  const fallback = DEFAULT_ARTWORK[kind]?.url
  if (fallback) return { kind, imageUrl: fallback, source: 'default' }
  return { kind, imageUrl: '', source: 'icon' }
}

/** 空态插画：只有真实文件存在时才返回 url，否则交给语义图标。 */
export function resolveEmptyArtwork(kind: EmptyArtworkKind): string {
  return EMPTY_ARTWORK[kind]?.url ?? ''
}
