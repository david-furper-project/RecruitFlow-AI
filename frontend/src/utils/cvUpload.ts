export const MAX_CV_SIZE_BYTES = 3 * 1024 * 1024;
export const MAX_CV_SIZE_LABEL = '3 MB';
export const CV_ACCEPT = '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document';

export const CANDIDATE_CV_MAX_SIZE_BYTES = MAX_CV_SIZE_BYTES;
export const CANDIDATE_CV_MAX_SIZE_LABEL = MAX_CV_SIZE_LABEL;
export const CANDIDATE_CV_ACCEPT = CV_ACCEPT;

type CvValidationOptions = {
  allowedExtensions?: string[];
  maxSizeBytes?: number;
  maxSizeLabel?: string;
};

export const CANDIDATE_CV_VALIDATION: CvValidationOptions = {
  allowedExtensions: ['.pdf', '.doc', '.docx'],
  maxSizeBytes: CANDIDATE_CV_MAX_SIZE_BYTES,
  maxSizeLabel: CANDIDATE_CV_MAX_SIZE_LABEL,
};

export const SOURCING_CV_ACCEPT = CV_ACCEPT;
export const SOURCING_CV_VALIDATION: CvValidationOptions = {
  allowedExtensions: ['.pdf', '.doc', '.docx'],
  maxSizeBytes: MAX_CV_SIZE_BYTES,
  maxSizeLabel: MAX_CV_SIZE_LABEL,
};

export function validateCvFile(file: File, options: CvValidationOptions = {}): string | null {
  const allowedExtensions = options.allowedExtensions || ['.pdf', '.doc', '.docx'];
  const maxSizeBytes = options.maxSizeBytes || MAX_CV_SIZE_BYTES;
  const maxSizeLabel = options.maxSizeLabel || MAX_CV_SIZE_LABEL;
  const extension = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
  if (!allowedExtensions.includes(extension)) {
    return `Formato no permitido. Adjunta un archivo ${allowedExtensions.join(', ')}.`;
  }
  if (file.size === 0) {
    return 'El CV está vacío.';
  }
  if (file.size > maxSizeBytes) {
    return `El CV supera el máximo permitido de ${maxSizeLabel}.`;
  }
  return null;
}

export function selectSingleCv(files: FileList | null, options: CvValidationOptions = {}): { file: File | null; error: string } {
  if (!files || files.length === 0) return { file: null, error: '' };
  if (files.length !== 1) {
    return { file: null, error: 'Solo puedes adjuntar un CV por postulación.' };
  }
  const file = files[0];
  const error = validateCvFile(file, options);
  return error ? { file: null, error } : { file, error: '' };
}

export function selectCvBatch(files: FileList | null, maxFiles = 20, options: CvValidationOptions = {}): { files: File[]; error: string } {
  const selected = Array.from(files || []);
  if (selected.length === 0) return { files: [], error: '' };
  if (selected.length > maxFiles) {
    return { files: [], error: `Puedes seleccionar hasta ${maxFiles} CV por lote.` };
  }
  const validFiles: File[] = [];
  const rejectedFiles: string[] = [];
  for (const file of selected) {
    const error = validateCvFile(file, options);
    if (error) rejectedFiles.push(`${file.name}: ${error}`);
    else validFiles.push(file);
  }
  return {
    files: validFiles,
    error: rejectedFiles.length
      ? `${rejectedFiles.length} archivo(s) no se incluyeron. ${rejectedFiles.join(' ')}`
      : '',
  };
}
