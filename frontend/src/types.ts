export type Role = 'doctor' | 'nurse' | 'billing_executive' | 'technician' | 'admin';

export interface User {
  username: string;
  token: string;
  role: Role;
  full_name: string;
  department?: string;
}

export interface SourceCitation {
  source_document: string;
  section_title: string;
  collection: string;
}

export interface Message {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  sources?: SourceCitation[];
  retrieval_type?: 'hybrid_rag' | 'sql_rag' | 'input_guardrail';
  role?: string;
  status?: string;
  timestamp: string;
}

export interface DemoAccount {
  username: string;
  full_name: string;
  role: Role;
  department: string;
  accessible_collections: string[];
}
