/*
 * Novel Landing —— 游戏式存档选择。
 *
 * 目标：作者打开产品 5 秒内知道「继续创作 / 新建小说」，不需要理解任何内部模块。
 */
import { useState } from 'react'
import Icon from './design-system/icons/IconRegistry'
import {
  Badge, Button, Card, EmptyState, ErrorState, LoadingState, ProgressBar,
} from './design-system/primitives'
import { EntityVisual } from './design-system/components'
import type { LandingCardViewModel } from './viewmodel'

export default function NovelLanding({ cards, loading, error, onRetry, onOpen, onCreate,
  onRename, onDelete }: {
  cards: LandingCardViewModel[]
  loading: boolean
  error: string
  onRetry: () => void
  onOpen: (novelId: string) => void
  onCreate: (novelId: string, title: string) => Promise<void>
  /** NF-011：重命名（只改作者可见名字）。 */
  onRename: (novelId: string, title: string) => Promise<void>
  /** NF-011：删除＝整体归档（需要二次确认，可恢复）。 */
  onDelete: (novelId: string) => Promise<void>
}) {
  const [creating, setCreating] = useState(false)
  const [draftId, setDraftId] = useState('')
  const [busy, setBusy] = useState(false)
  const [localError, setLocalError] = useState('')
  /** NF-011：卡片上的管理动作（重命名 / 删除）在同一处确认，避免误删。 */
  const [manageId, setManageId] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState('')
  const [manageBusy, setManageBusy] = useState(false)
  const [manageError, setManageError] = useState('')
  const [manageNotice, setManageNotice] = useState('')

  const openManage = (card: LandingCardViewModel) => {
    setManageId(card.novelId)
    setRenameValue(card.title)
    setConfirmDelete('')
    setManageError('')
    setManageNotice('')
  }

  const submitRename = async () => {
    if (!manageId) return
    setManageBusy(true); setManageError(''); setManageNotice('')
    try {
      await onRename(manageId, renameValue.trim())
      setManageNotice('作品名已经更新。')
    } catch (reason) {
      setManageError(reason instanceof Error ? reason.message : String(reason))
    } finally { setManageBusy(false) }
  }

  const submitDelete = async () => {
    if (!manageId) return
    setManageBusy(true); setManageError(''); setManageNotice('')
    try {
      await onDelete(manageId)
      setManageId('')
      setConfirmDelete('')
      setManageNotice('作品已经归档：它从列表里消失，产物整体保留在归档目录里。')
    } catch (reason) {
      setManageError(reason instanceof Error ? reason.message : String(reason))
    } finally { setManageBusy(false) }
  }

  const submit = async () => {
    const novelId = draftId.trim()
    if (novelId.length < 3) { setLocalError('作品编号至少 3 个字符'); return }
    setBusy(true); setLocalError('')
    try {
      await onCreate(novelId, novelId)
      setDraftId(''); setCreating(false)
    } catch (reason) {
      setLocalError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const recent = cards[0]

  return (
    <div className="v3-landing" data-testid="v3-landing">
      <header className="v3-landing-head">
        <div className="v3-landing-brand">
          <span className="v3-nav-mark" aria-hidden="true"><Icon name="book" size={22} /></span>
          <div>
            <h1>NovelForge</h1>
            <p>选一本作品继续，或者开一本新的。</p>
          </div>
        </div>
        <div className="v3-landing-actions">
          <Button variant="secondary" icon="add" onClick={() => setCreating((v) => !v)}
            testId="v3-landing-new">新建小说</Button>
          {recent ? <Button variant="primary" iconAfter="next_action"
            onClick={() => onOpen(recent.novelId)} testId="v3-landing-continue">
            继续创作
          </Button> : null}
        </div>
      </header>

      {creating && <Card className="v3-landing-create" tone="elevated" testId="v3-landing-create">
        <h2>新建小说</h2>
        <p>先给作品一个编号；题材、世界与角色会在创作流程里一步步建立。</p>
        <label className="v3-field">
          <span>作品编号</span>
          <input value={draftId} maxLength={64} placeholder="例如 novel_sea_city"
            aria-label="新作品编号" onChange={(event) => setDraftId(event.target.value)} />
        </label>
        {localError ? <p className="v3-field-error" role="alert">{localError}</p> : null}
        <div className="v3-landing-create-actions">
          <Button variant="primary" disabled={busy} onClick={submit}
            testId="v3-landing-create-submit">{busy ? '正在创建…' : '开始创作'}</Button>
          <Button variant="ghost" onClick={() => { setCreating(false); setLocalError('') }}>取消</Button>
        </div>
      </Card>}

      {loading ? <LoadingState label="正在读取你的作品…" /> : null}
      {error ? <ErrorState message={error} onRetry={onRetry} /> : null}

      {!loading && !error && cards.length === 0 && (
        <EmptyState icon="creation" title="还没有作品"
          reason="作品是这一切的起点：它保存你的设定、推演与大纲。"
          value="创建第一本作品后，系统会告诉你下一步该做什么。"
          action={<Button variant="primary" icon="add" onClick={() => setCreating(true)}>
            创建第一本作品
          </Button>} />
      )}

      {cards.length > 0 && (
        <section className="v3-landing-section">
          <h2 className="v3-landing-section-title">
            <Icon name="chapter" size={18} />最近作品
          </h2>
          <ul className="v3-landing-grid" data-testid="v3-landing-grid">
            {cards.map((card) => (
              <Card as="li" key={card.novelId} className="v3-novel-card" tone="default"
                testId={`v3-novel-card-${card.novelId}`}>
                <div className="v3-novel-card-visual" aria-hidden="true">
                  {/* 作品封面永远走 Artwork Manifest（真实封面 → 产品默认 → 语义图标）。 */}
                  <EntityVisual visual={card.visual} size="fill"
                    testId={`v3-novel-cover-${card.novelId}`} />
                </div>
                <div className="v3-novel-card-body">
                  <div className="v3-novel-card-head">
                    <h3>{card.title}</h3>
                    <Badge tone="neutral" icon={card.stageIcon}>{card.stageLabel}</Badge>
                  </div>
                  {card.tags.length > 0 && <div className="v3-novel-card-tags">
                    {card.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>}
                  <ProgressBar percent={card.progressPercent} label={card.progressLabel}
                    testId={`v3-novel-card-progress-${card.novelId}`} />
                  <p className="v3-novel-card-next" data-testid={`v3-novel-next-${card.novelId}`}>
                    <Icon name="next_action" size={15} />下一步：{card.nextAction}
                  </p>
                  <div className="v3-novel-card-foot">
                    <small>{card.updatedLabel ? `最近编辑 ${card.updatedLabel}` : ''}</small>
                    <span className="v3-novel-card-buttons">
                      <Button variant="ghost" size="sm"
                        onClick={() => openManage(card)}
                        testId={`v3-novel-manage-${card.novelId}`}>管理</Button>
                      <Button variant="primary" size="sm" iconAfter="next_action"
                        onClick={() => onOpen(card.novelId)}
                        testId={`v3-novel-continue-${card.novelId}`}>继续创作</Button>
                    </span>
                  </div>
                  {manageId === card.novelId ? (
                    <div className="v3-novel-manage" data-testid={`v3-novel-manage-panel-${card.novelId}`}>
                      <label className="v3-field">
                        <span>作品名</span>
                        <input value={renameValue} maxLength={120}
                          aria-label="作品名"
                          onChange={(event) => setRenameValue(event.target.value)} />
                      </label>
                      <div className="v3-flow-actions">
                        <Button variant="secondary" size="sm" disabled={manageBusy}
                          onClick={() => { void submitRename() }}
                          testId={`v3-novel-rename-submit-${card.novelId}`}>
                          {manageBusy ? '正在保存…' : '保存新名字'}</Button>
                        <Button variant="ghost" size="sm"
                          onClick={() => setManageId('')}>取消</Button>
                      </div>
                      <p className="v3-context-why">
                        <Icon name="warning" size={15} />
                        删除＝把这本作品的全部产物整体归档：大纲、事实、内容包与写作草稿
                        一起移入归档目录（可恢复），不会留下孤儿文件。
                      </p>
                      <label className="v3-field">
                        <span>要删除请再输入一次作品编号</span>
                        <input value={confirmDelete} maxLength={96}
                          aria-label="确认删除作品编号"
                          placeholder={card.novelId}
                          onChange={(event) => setConfirmDelete(event.target.value)} />
                      </label>
                      <div className="v3-flow-actions">
                        <Button variant="danger" size="sm" disabled={manageBusy
                          || confirmDelete.trim() !== card.novelId}
                          onClick={() => { void submitDelete() }}
                          testId={`v3-novel-delete-submit-${card.novelId}`}>
                          {manageBusy ? '正在归档…' : '删除这本作品'}</Button>
                      </div>
                      {manageError ? <p className="v3-field-error" role="alert"
                        data-testid={`v3-novel-manage-error-${card.novelId}`}>{manageError}</p> : null}
                    </div>
                  ) : null}
                </div>
              </Card>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
