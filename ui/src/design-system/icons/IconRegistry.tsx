/*
 * NovelForge V3 IconRegistry
 *
 * 一个概念 = 一个语义图标 id。产品里任何地方需要图标都必须通过 <Icon name=... />，
 * 不允许组件各自找 SVG，也不允许 emoji。
 *
 * 风格：24x24 网格、中等描边（1.7）、圆角端点，20–28px 下可辨认。
 */
import type { CSSProperties } from 'react'

export const ICON_STROKE = 1.7

const PATHS: Record<string, JSX.Element> = {
  home: <><path d="M4 10.5 12 4l8 6.5" /><path d="M6 10v9h12v-9" /><path d="M10 19v-5h4v5" /></>,
  creation: <><path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.5l-1.9-5.7L4.5 11l5.6-2z" /><path d="M18.5 16.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" /></>,
  world: <><circle cx="12" cy="12" r="8.2" /><path d="M3.8 12h16.4" /><path d="M12 3.8c2.4 2.3 3.6 5 3.6 8.2s-1.2 5.9-3.6 8.2c-2.4-2.3-3.6-5-3.6-8.2S9.6 6.1 12 3.8z" /></>,
  character: <><circle cx="12" cy="8.4" r="3.6" /><path d="M5 20c0-3.6 3.1-6.2 7-6.2s7 2.6 7 6.2" /></>,
  location: <><path d="M12 21s6.4-6.2 6.4-11A6.4 6.4 0 0 0 5.6 10c0 4.8 6.4 11 6.4 11z" /><circle cx="12" cy="10" r="2.4" /></>,
  faction: <><path d="M6 3.6v16.8" /><path d="M6 5.4h11.6l-2.3 3.4 2.3 3.4H6" /></>,
  relationship: <><circle cx="7.5" cy="7.5" r="2.6" /><circle cx="16.5" cy="16.5" r="2.6" /><path d="M9.4 9.4 14.6 14.6" /><path d="M16.5 6.5v3" /><path d="M7.5 14.5v3" /></>,
  story: <><path d="M4.5 5.2c2.6-1.1 5-1.1 7.5.3 2.5-1.4 4.9-1.4 7.5-.3v13c-2.6-1.1-5-1.1-7.5.3-2.5-1.4-4.9-1.4-7.5-.3z" /><path d="M12 5.5v13" /></>,
  route: <><circle cx="6" cy="6.2" r="2.2" /><circle cx="18" cy="17.8" r="2.2" /><path d="M6 8.4c0 4 2.4 5.4 5.4 5.4H13" /><path d="M13 13.8h5v4" /></>,
  simulation: <><path d="M12 3.6 20 8v8l-8 4.4L4 16V8z" /><path d="M12 12.4 20 8" /><path d="M12 12.4V20" /><path d="M12 12.4 4 8" /></>,
  chapter: <><path d="M6 3.8h9.6L19 7.2V20H6z" /><path d="M15.2 4v3.6H19" /><path d="M9 12h7" /><path d="M9 15.6h7" /></>,
  outline: <><path d="M4.5 6.5h6" /><path d="M4.5 12h9" /><path d="M4.5 17.5h6" /><path d="M17 9.5v9" /><path d="M14 16.5l3 3 3-3" /></>,
  review: <><path d="M12 3.4 19 6v6c0 4.2-2.9 7.4-7 8.6-4.1-1.2-7-4.4-7-8.6V6z" /><path d="M9 11.8l2.2 2.2L15.4 10" /></>,
  warning: <><path d="M12 4.2 21 19.4H3z" /><path d="M12 9.6v4.4" /><path d="M12 16.6v.1" /></>,
  repair: <><path d="M14.5 6.5a3.6 3.6 0 0 1 4.9 4.9l-8 8-3.2.8.8-3.2z" /><path d="M4.5 4.5 9 9" /></>,
  export: <><path d="M12 4v10" /><path d="M8.4 10.6 12 14.2l3.6-3.6" /><path d="M5 17.4V20h14v-2.6" /></>,
  objective: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.4" /><path d="M12 1.8v3" /><path d="M12 19.2v3" /><path d="M1.8 12h3" /><path d="M19.2 12h3" /></>,
  next_action: <><path d="M4.5 12h13" /><path d="M12.5 7 18 12l-5.5 5" /><path d="M21 12" /></>,
  locked: <><rect x="5.2" y="10.4" width="13.6" height="9.4" rx="2" /><path d="M8.4 10.4V8a3.6 3.6 0 0 1 7.2 0v2.4" /></>,
  complete: <><circle cx="12" cy="12" r="8.2" /><path d="M8.2 12.4 11 15.2l5-5.4" /></>,
  current: <><circle cx="12" cy="12" r="8.6" /><circle cx="12" cy="12" r="3.6" /></>,
  progress: <><path d="M4.5 16.5a8 8 0 1 1 15 0" /><path d="M12 12.6 16 9" /></>,
  settings: <><circle cx="12" cy="12" r="2.8" /><path d="M12 3.6v2.2M12 18.2v2.2M3.6 12h2.2M18.2 12h2.2M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M17.9 6.1l-1.6 1.6M7.7 16.3l-1.6 1.6" /></>,
  search: <><circle cx="11" cy="11" r="6.2" /><path d="M15.6 15.6 20 20" /></>,
  bell: <><path d="M6.6 10.4a5.4 5.4 0 0 1 10.8 0c0 4 1.6 5.4 1.6 5.4H5s1.6-1.4 1.6-5.4z" /><path d="M10 18.6a2.2 2.2 0 0 0 4 0" /></>,
  close: <><path d="M6.5 6.5 17.5 17.5" /><path d="M17.5 6.5 6.5 17.5" /></>,
  back: <><path d="M10 6 4 12l6 6" /><path d="M4 12h16" /></>,
  more: <><circle cx="6" cy="12" r="1.3" /><circle cx="12" cy="12" r="1.3" /><circle cx="18" cy="12" r="1.3" /></>,
  conflict: <><path d="M12 3.2 15 9.6l6.6.6-4.8 4.4 1.3 6.4L12 17.6 5.9 21l1.3-6.4L2.4 10.2l6.6-.6z" /></>,
  foreshadow: <><path d="M3.6 12c2.8-4.2 5.4-6.2 8.4-6.2s5.6 2 8.4 6.2c-2.8 4.2-5.4 6.2-8.4 6.2S6.4 16.2 3.6 12z" /><circle cx="12" cy="12" r="2.6" /></>,
  progression: <><path d="M4.6 19.4V13" /><path d="M10 19.4V9" /><path d="M15.4 19.4V11" /><path d="M20 19.4V5.6" /></>,
  add: <><path d="M12 5.4v13.2" /><path d="M5.4 12h13.2" /></>,
  book: <><path d="M5 4.6h13.4v14.8H5z" /><path d="M5 8.4h13.4" /><path d="M8.4 4.6v3.8" /></>,
}

export const ICON_IDS = Object.keys(PATHS)

export type IconName = keyof typeof PATHS | string

export interface IconProps {
  name: IconName
  size?: number
  /** 语义标题；给了 title 时图标对辅助技术可见。 */
  title?: string
  className?: string
  style?: CSSProperties
}

export default function Icon({ name, size = 22, title, className = '', style }: IconProps) {
  const glyph = PATHS[name] ?? PATHS.current
  return (
    <svg
      className={`v3-icon ${className}`.trim()}
      style={style}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={ICON_STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : 'presentation'}
      aria-hidden={title ? undefined : true}
      focusable="false"
      data-icon={name}
    >
      {title ? <title>{title}</title> : null}
      {glyph}
    </svg>
  )
}

/** 阶段 / 状态 → 图标（同一状态全产品只用一个图标）。 */
export const STATUS_ICON: Record<string, string> = {
  COMPLETE: 'complete',
  CURRENT: 'current',
  IN_PROGRESS: 'progress',
  AVAILABLE: 'current',
  LOCKED: 'locked',
  WARNING: 'warning',
  BLOCKED: 'warning',
}

export const STATUS_LABEL: Record<string, string> = {
  COMPLETE: '已完成',
  CURRENT: '进行中',
  IN_PROGRESS: '进行中',
  AVAILABLE: '可进入',
  LOCKED: '尚未开放',
  WARNING: '需要留意',
  BLOCKED: '需要处理',
}
