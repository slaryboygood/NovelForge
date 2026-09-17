import { Component } from 'react'
import type { ReactNode } from 'react'

/**
 * 面板级错误边界。
 *
 * 一个高级工具面板渲染失败时，不应该把整个创作工作台打成白屏：
 * 作者至少还能切换页签、使用其它面板。切换页签时自动复位。
 */
interface Props {
  resetKey: string
  label: string
  children: ReactNode
}

interface State {
  error: string
}

export default class PanelBoundary extends Component<Props, State> {
  state: State = { error: '' }

  static getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error.message : String(error) }
  }

  componentDidUpdate(previous: Props) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: '' })
    }
  }

  render() {
    if (this.state.error) {
      return <section className="world-panel" data-testid="panel-boundary-error">
        <div className="world-panel-head">
          <div>
            <span className="story-builder-kicker">面板错误</span>
            <h3>「{this.props.label}」暂时无法显示</h3>
          </div>
        </div>
        <p className="world-empty">原因：{this.state.error}</p>
        <p className="world-source">其它面板不受影响，可以切换页签继续工作。</p>
      </section>
    }
    return this.props.children
  }
}
