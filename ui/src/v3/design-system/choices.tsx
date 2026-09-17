/*
 * V3 选择组件：ChoiceCard（候选对象）与 FeedbackCard（游戏式反馈）。
 *
 * 候选卡只负责展示与选中态：标题、简述、适配理由、来源；不做业务判断。
 * 反馈卡只表达四件事：发生了什么、进度怎么变、解锁了什么、下一步去哪。
 */
import Icon from './icons/IconRegistry'
import { Card } from './primitives'

export interface ChoiceCardProps {
  title: string
  summary?: string
  reason?: string
  source?: string
  selected: boolean
  multi?: boolean
  disabled?: boolean
  impactNote?: string
  testId?: string
  onToggle: () => void
}

export function ChoiceCard({ title, summary = '', reason = '', source = '',
  selected, multi = false, disabled = false, impactNote = '', testId,
  onToggle }: ChoiceCardProps) {
  return (
    <Card as="div" className={`v3-choice ${selected ? 'is-selected' : ''}`}
      tone="default" selected={selected} testId={testId}>
      <button type="button" className="v3-choice-hit" disabled={disabled}
        aria-pressed={selected}
        aria-label={`${title}${selected ? '（已选择）' : ''}`}
        onClick={onToggle}>
        <span className="v3-choice-mark" aria-hidden="true">
          {selected ? <Icon name="complete" size={18} /> : <span className="v3-choice-empty" />}
        </span>
        <span className="v3-choice-body">
          <b>{title}</b>
          {summary ? <p>{summary}</p> : null}
          {reason ? <p className="v3-choice-reason">适合你的原因：{reason}</p> : null}
          {source ? <small>{source}</small> : null}
          {impactNote ? <small>{impactNote}</small> : null}
        </span>
        <span className="v3-choice-flag">
          {selected ? '已选' : multi ? '可多选' : '未选'}
        </span>
      </button>
    </Card>
  )
}

export interface FeedbackViewModel {
  title: string
  stageProgress: string
  unlock: string
  next: string
}

export function FeedbackCard({ feedback, onDismiss }: {
  feedback: FeedbackViewModel
  onDismiss: () => void
}) {
  return (
    <div className="v3-feedback" role="status" data-testid="v3-feedback">
      <span className="v3-feedback-icon" aria-hidden="true"><Icon name="complete" size={20} /></span>
      <div className="v3-feedback-body">
        <b data-testid="v3-feedback-title">{feedback.title}</b>
        {feedback.stageProgress
          ? <p data-testid="v3-feedback-progress">{feedback.stageProgress}</p> : null}
        {feedback.unlock ? <p className="v3-feedback-unlock">
          {/* NF-017：前缀只加一次——投影给的 unlock 文案本身可能已经带「解锁：」。 */}
          <Icon name="next_action" size={14} />
          已解锁：{feedback.unlock.replace(/^(已)?解锁：/, '')}
        </p> : null}
        {feedback.next ? <p className="v3-feedback-next">
          下一步：{feedback.next}
        </p> : null}
      </div>
      <button type="button" className="v3-icon-btn v3-icon-btn-ghost" aria-label="关闭提示"
        onClick={onDismiss}><Icon name="close" size={16} /></button>
    </div>
  )
}
