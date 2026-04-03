export type Citation = {
  chunk_id: number;
  file_id: number;
  filename: string;
  snippet: string;
};

export type ChatResponse = {
  request_id: string;
  answer: string;
  citations: Citation[];
  metadata: Record<string, number | string>;
};

export type ModelResponse = {
  active: string;
  available: string[];
  profiles: Record<string, number>;
};

export type DocumentItem = {
  id: number;
  title: string;
  content: string;
  updated_at: string;
};

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function apiUrl(): string {
  return API_URL;
}

export async function getModels(): Promise<ModelResponse> {
  const r = await fetch(`${API_URL}/models`);
  if (!r.ok) throw new Error('Unable to load models');
  return r.json();
}

export async function selectModel(model: string): Promise<void> {
  const r = await fetch(`${API_URL}/models/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model })
  });
  if (!r.ok) throw new Error('Unable to switch model');
}

export async function sendChat(message: string, model: string, document_content: string): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, model, document_content })
  });
  if (!r.ok) throw new Error('Chat request failed');
  return r.json();
}

export async function uploadFile(file: File): Promise<void> {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`${API_URL}/files/upload`, {
    method: 'POST',
    body: form
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function deleteFile(fileId: number): Promise<void> {
  const r = await fetch(`${API_URL}/files/${fileId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error('Delete failed');
}

export async function listFiles(): Promise<Array<{ id: number; filename: string; uploaded_at: string }>> {
  const r = await fetch(`${API_URL}/files`);
  if (!r.ok) throw new Error('Unable to load files');
  const payload = await r.json();
  return payload.items || [];
}

export async function transformText(operation: 'summarize' | 'improve' | 'rewrite', selected_text: string, model: string): Promise<string> {
  const r = await fetch(`${API_URL}/editor/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operation, selected_text, model })
  });
  if (!r.ok) throw new Error('Transform failed');
  const payload = await r.json();
  return payload.transformed_text;
}

export async function listDocuments(): Promise<DocumentItem[]> {
  const r = await fetch(`${API_URL}/documents`);
  if (!r.ok) throw new Error('Unable to load documents');
  const payload = await r.json();
  return payload.items || [];
}

export async function getDocument(docId: number): Promise<DocumentItem> {
  const r = await fetch(`${API_URL}/documents/${docId}`);
  if (!r.ok) throw new Error('Unable to load document');
  return r.json();
}
