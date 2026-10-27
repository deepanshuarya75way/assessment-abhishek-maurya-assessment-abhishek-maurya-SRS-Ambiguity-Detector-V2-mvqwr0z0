/** Privacy/data-lifecycle types — mirrored from the project contract */

export interface PrivacySettings {
  history_retention_days: number | null;
}

export interface UpdatePrivacySettingsInput {
  history_retention_days: number | null;
}

export interface PrivacyExportTicket {
  export_id: string;
  download_url: string;
  expires_at: string;
}

export interface PrivacyPurgeInput {
  older_than_days?: number;
}

export interface PrivacyPurgeResult {
  deleted_analyses: number;
  deleted_documents: number;
}
