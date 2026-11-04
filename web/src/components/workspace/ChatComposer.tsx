interface Props {
  draft: string;
  disabled: boolean;
  busy: boolean;
  onDraftChange: (draft: string) => void;
  onSend: () => void;
}

export default function ChatComposer({ draft, disabled, busy, onDraftChange, onSend }: Props) {
  return <form onSubmit={event => { event.preventDefault(); onSend(); }}>
    <input placeholder="输入学习问题…" value={draft} disabled={disabled} onChange={event => onDraftChange(event.target.value)} />
    <button type="submit" disabled={disabled || busy}>发送</button>
  </form>;
}
