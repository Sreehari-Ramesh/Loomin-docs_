import { useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Heading from '@tiptap/extension-heading';
import Placeholder from '@tiptap/extension-placeholder';
import TurndownService from 'turndown';
import { marked } from 'marked';

import {
  apiUrl,
  deleteFile,
  getDocument,
  getModels,
  listDocuments,
  listFiles,
  selectModel,
  sendChat,
  transformText,
  uploadFile,
  type Citation
} from './api';

type ChatItem = {
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  requestId?: string;
};

function tokenEstimate(text: string): number {
  return Math.max(1, Math.floor(text.length / 4));
}

function Toolbar({
  onTransform,
  markdownMode,
  toggleMarkdown
}: {
  onTransform: (op: 'summarize' | 'improve' | 'rewrite') => Promise<void>;
  markdownMode: boolean;
  toggleMarkdown: () => void;
}) {
  return (
    <div className="toolbar">
      <button onClick={() => onTransform('summarize')}>Summarize</button>
      <button onClick={() => onTransform('improve')}>Improve</button>
      <button onClick={() => onTransform('rewrite')}>Rewrite</button>
      <button onClick={toggleMarkdown}>{markdownMode ? 'Rich Text Mode' : 'Markdown Mode'}</button>
    </div>
  );
}

const turndown = new TurndownService();

export default function App() {
  const [tab, setTab] = useState<'chat' | 'files'>('chat');
  const [models, setModels] = useState<string[]>([]);
  const [modelProfiles, setModelProfiles] = useState<Record<string, number>>({});
  const [activeModel, setActiveModel] = useState('llama3:8b');
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [files, setFiles] = useState<Array<{ id: number; filename: string; uploaded_at: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [contextPct, setContextPct] = useState(0);
  const [retrievedTokens, setRetrievedTokens] = useState(0);
  const [peers, setPeers] = useState(1);
  const [docId, setDocId] = useState<number>(1);
  const [markdownMode, setMarkdownMode] = useState(false);
  const [markdownValue, setMarkdownValue] = useState('');
  const [highlightCitation, setHighlightCitation] = useState<Citation | null>(null);

  const suppressLocalSync = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Heading.configure({ levels: [1, 2, 3] }),
      Placeholder.configure({ placeholder: 'Write your document...' })
    ],
    content: '<h2>Loomin Docs Workspace</h2><p>Loading...</p>',
    onUpdate({ editor: current }) {
      if (suppressLocalSync.current) return;
      const html = current.getHTML();
      setMarkdownValue(turndown.turndown(html));
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'sync', content: html }));
      }
    }
  });

  useEffect(() => {
    async function init() {
      const m = await getModels();
      setModels(m.available);
      setModelProfiles(m.profiles || {});
      setActiveModel(m.active);
      setFiles(await listFiles());
      const docs = await listDocuments();
      const initialDoc = docs[0] || (await getDocument(1));
      setDocId(initialDoc.id);
      if (editor) {
        suppressLocalSync.current = true;
        editor.commands.setContent(initialDoc.content || '<p></p>');
        suppressLocalSync.current = false;
        setMarkdownValue(turndown.turndown(initialDoc.content || ''));
      }
    }

    init().catch(console.error);
  }, [editor]);

  useEffect(() => {
    if (!editor || !docId) return;
    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = new URL(apiUrl()).host;
    const socket = new WebSocket(`${wsProto}://${host}/ws/documents/${docId}?client_id=${crypto.randomUUID()}`);
    wsRef.current = socket;

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'init') {
        setPeers(msg.peers || 1);
        suppressLocalSync.current = true;
        editor.commands.setContent(msg.content || '<p></p>');
        suppressLocalSync.current = false;
        setMarkdownValue(turndown.turndown(msg.content || ''));
      } else if (msg.type === 'sync') {
        suppressLocalSync.current = true;
        editor.commands.setContent(msg.content || '<p></p>');
        suppressLocalSync.current = false;
        setMarkdownValue(turndown.turndown(msg.content || ''));
      } else if (msg.type === 'presence') {
        setPeers(msg.peers || 1);
      }
    };

    return () => {
      socket.close();
      wsRef.current = null;
    };
  }, [editor, docId]);

  const docText = editor?.getText() || '';
  const docTokens = tokenEstimate(docText);
  const contextWindow = modelProfiles[activeModel] || 8192;

  const displayContextPct = useMemo(() => {
    if (contextPct > 0) return contextPct;
    return Number((((docTokens + retrievedTokens) / contextWindow) * 100).toFixed(2));
  }, [contextPct, contextWindow, docTokens, retrievedTokens]);

  async function runTransform(op: 'summarize' | 'improve' | 'rewrite') {
    if (!editor) return;
    const selected = editor.state.doc.textBetween(
      editor.state.selection.from,
      editor.state.selection.to,
      ' '
    );
    if (!selected.trim()) return;

    setBusy(true);
    try {
      const result = await transformText(op, selected, activeModel);
      editor.chain().focus().insertContent(result).run();
    } finally {
      setBusy(false);
    }
  }

  async function onSendChat() {
    if (!chatInput.trim() || !editor) return;
    const userText = chatInput;
    setChatInput('');
    setBusy(true);
    setMessages((prev) => [...prev, { role: 'user', text: userText }]);
    try {
      const res = await sendChat(userText, activeModel, editor.getText());
      const pct = Number(res.metadata.context_used_pct || 0);
      setContextPct(pct);
      setRetrievedTokens(Number(res.metadata.retrieved_tokens || 0));
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: res.answer,
          citations: res.citations,
          requestId: res.request_id
        }
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function onModelChange(model: string) {
    setActiveModel(model);
    await selectModel(model);
  }

  async function onUpload(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      await uploadFile(file);
      setFiles(await listFiles());
    } finally {
      setBusy(false);
      ev.target.value = '';
    }
  }

  async function onDeleteFile(fileId: number) {
    setBusy(true);
    try {
      await deleteFile(fileId);
      setFiles(await listFiles());
    } finally {
      setBusy(false);
    }
  }

  function toggleMarkdown() {
    if (!editor) return;
    if (!markdownMode) {
      setMarkdownValue(turndown.turndown(editor.getHTML()));
      setMarkdownMode(true);
      return;
    }

    const html = marked.parse(markdownValue) as string;
    suppressLocalSync.current = true;
    editor.commands.setContent(html);
    suppressLocalSync.current = false;
    setMarkdownMode(false);
  }

  return (
    <div className="app-shell">
      <main className="editor-pane">
        <header className="editor-header">
          <h1>Loomin Docs</h1>
          <div className="presence-pill">Live collaborators: {peers}</div>
          <div className="token-meter">
            <span>Context Used ({activeModel})</span>
            <div className="meter-track">
              <div className="meter-fill" style={{ width: `${Math.min(displayContextPct, 100)}%` }} />
            </div>
            <small>
              {displayContextPct}% of {contextWindow} tokens (doc: {docTokens}, retrieved: {retrievedTokens})
            </small>
          </div>
        </header>

        <Toolbar onTransform={runTransform} markdownMode={markdownMode} toggleMarkdown={toggleMarkdown} />
        <section className="editor-canvas">
          {markdownMode ? (
            <textarea
              className="markdown-editor"
              value={markdownValue}
              onChange={(e) => setMarkdownValue(e.target.value)}
            />
          ) : (
            <EditorContent editor={editor} />
          )}
        </section>
      </main>

      <aside className="side-panel">
        <div className="model-row">
          <label>Model</label>
          <select value={activeModel} onChange={(e) => onModelChange(e.target.value)}>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <div className="tabs">
          <button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>
            Chat
          </button>
          <button className={tab === 'files' ? 'active' : ''} onClick={() => setTab('files')}>
            Files
          </button>
        </div>

        {tab === 'chat' ? (
          <div className="chat-tab">
            <div className="chat-list">
              {messages.map((m, i) => (
                <article key={i} className={`bubble ${m.role}`}>
                  <p>{m.text}</p>
                  {m.requestId && <small>request_id: {m.requestId}</small>}
                  {m.citations && m.citations.length > 0 && (
                    <ul>
                      {m.citations.map((c) => (
                        <li key={c.chunk_id}>
                          <button className="citation-btn" onClick={() => setHighlightCitation(c)}>
                            [{c.filename}] chunk:{c.chunk_id}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>
            <div className="chat-input-row">
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask the assistant..."
              />
              <button disabled={busy} onClick={onSendChat}>
                Send
              </button>
            </div>
          </div>
        ) : (
          <div className="files-tab">
            <label className="upload-btn">
              Upload (.pdf/.md/.txt)
              <input type="file" accept=".pdf,.md,.txt" onChange={onUpload} />
            </label>
            <ul className="file-list">
              {files.map((f) => (
                <li key={f.id}>
                  <strong>{f.filename}</strong>
                  <span>{new Date(f.uploaded_at).toLocaleString()}</span>
                  <button className="danger" onClick={() => onDeleteFile(f.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {highlightCitation && (
          <div className="citation-preview">
            <strong>
              {highlightCitation.filename} / chunk:{highlightCitation.chunk_id}
            </strong>
            <p>{highlightCitation.snippet}</p>
            <button onClick={() => setHighlightCitation(null)}>Close</button>
          </div>
        )}
      </aside>
    </div>
  );
}
