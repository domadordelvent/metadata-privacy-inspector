'use strict';

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tif', 'tiff', 'ico', 'ppm', 'pgm', 'pbm', 'pdf', 'docx', 'xlsx', 'pptx', 'mp3', 'mp4', 'mov']);
const element = (id) => document.getElementById(id);
const form = element('upload-form');
const fileInput = element('file-input');
const dropZone = element('drop-zone');
const analyzeButton = element('analyze-button');
let selectedFile = null;
let busy = false;
let dragDepth = 0;
let inspectedFile = null;
let cleanUrl = null;
let cleaning = false;

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

function formatValue(value) {
  if (value === null) return '—';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function showError(message) {
  element('error-message').textContent = message;
  element('error-message').hidden = !message;
}

function resetSelection() {
  selectedFile = null;
  fileInput.value = '';
  analyzeButton.disabled = true;
  element('drop-title').textContent = 'Drop your file here';
  element('drop-description').textContent = 'or browse files to get started';
  element('selected-size').hidden = true;
}

function selectFiles(files) {
  if (busy) return;
  showError('');
  resetSelection();
  if (files.length !== 1) {
    if (files.length > 1) showError('Please select one file at a time.');
    return;
  }
  const file = files[0];
  if (file.size === 0) return showError('This file is empty. Choose another file.');
  if (file.size > MAX_FILE_BYTES) return showError('This file exceeds the 20 MiB limit. Choose a smaller file.');
  const extension = file.name.split('.').pop().toLowerCase();
  if (!SUPPORTED_EXTENSIONS.has(extension)) return showError('This file format is not supported. Choose one of the formats listed below.');
  selectedFile = file;
  element('drop-title').textContent = file.name;
  element('drop-description').textContent = 'Ready to inspect · Select or drop a file to replace it';
  element('selected-size').textContent = formatSize(file.size);
  element('selected-size').hidden = false;
  analyzeButton.disabled = false;
}

fileInput.addEventListener('change', () => selectFiles(Array.from(fileInput.files)));
dropZone.addEventListener('dragenter', (event) => {
  event.preventDefault();
  if (!busy) { dragDepth += 1; dropZone.classList.add('drag-over'); }
});
dropZone.addEventListener('dragover', (event) => {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = busy ? 'none' : 'copy';
});
dropZone.addEventListener('dragleave', (event) => {
  event.preventDefault();
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) dropZone.classList.remove('drag-over');
});
dropZone.addEventListener('drop', (event) => {
  event.preventDefault();
  dragDepth = 0;
  dropZone.classList.remove('drag-over');
  if (event.dataTransfer) selectFiles(Array.from(event.dataTransfer.files));
});
// Prevent an accidental drop outside the workspace from navigating to the file.
window.addEventListener('dragover', (event) => event.preventDefault());
window.addEventListener('drop', (event) => event.preventDefault());

function textNode(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderLocation(metadata, findings) {
  const values = element('gps-values');
  values.replaceChildren();
  const gps = metadata.GPS;
  let coordinates = null;
  if (gps && Number.isFinite(gps.latitude_decimal) && Number.isFinite(gps.longitude_decimal)) {
    coordinates = [gps.latitude_decimal, gps.longitude_decimal];
  } else {
    const finding = findings.find((item) => item.field === 'GPS' && Array.isArray(item.value) && item.value.length === 2 && item.value.every(Number.isFinite));
    if (finding) coordinates = finding.value;
  }
  if (coordinates) {
    ['LATITUDE', 'LONGITUDE'].forEach((label, index) => {
      const item = document.createElement('div');
      item.append(textNode('span', label, 'gps-coordinate-label'), textNode('strong', `${coordinates[index].toFixed(6)}°`, 'gps-coordinate-value'));
      values.append(item);
    });
  } else if (gps || metadata.Location) {
    const item = document.createElement('div');
    item.append(textNode('span', 'EMBEDDED LOCATION', 'gps-coordinate-label'), textNode('strong', formatValue(metadata.Location || gps), 'gps-coordinate-value'));
    values.append(item);
  }
  element('gps-panel').hidden = !values.childElementCount;
}

function hasSummaryValue(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.some(hasSummaryValue);
  if (typeof value === 'object') return Object.values(value).some(hasSummaryValue);
  return true;
}

function buildPrivacySummary(metadata, findings) {
  // Explain existing values only; do not infer identity, place or a risk score.
  const detected = new Map(Object.entries(metadata).filter(([, value]) => hasSummaryValue(value)));
  findings.forEach((finding) => {
    if (!detected.has(finding.field) && hasSummaryValue(finding.value)) detected.set(finding.field, finding.value);
  });
  const groups = [
    {
      title: 'Location', fields: ['GPS', 'Location'],
      explanation: 'Location metadata may reveal a place associated with this file.',
      recommendation: 'Remove location tags from a copy before sharing if the place should stay private.'
    },
    {
      title: 'Device', fields: ['Make', 'Model'],
      explanation: 'Device metadata may reveal the manufacturer or model used to create this file.',
      recommendation: 'Remove device tags from a sharing copy if you do not want to disclose this equipment.'
    },
    {
      title: 'Author and ownership', fields: ['Author', 'Artist', 'AlbumArtist', 'Composer', 'Copyright', 'LastModifiedBy'],
      explanation: 'Author or owner labels may reveal a name or who last edited the file. These labels do not prove identity.',
      recommendation: 'Review these labels and remove personal names from a copy when appropriate. Keep any required ownership notices.'
    },
    {
      title: 'Dates', fields: ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized', 'CreationDate', 'ModDate', 'Date'],
      explanation: 'Saved dates may reveal when this file was created, edited or recorded.',
      recommendation: 'Review the timestamps and remove them from a sharing copy if the timing is sensitive.'
    },
    {
      title: 'Software', fields: ['Software', 'Creator', 'Producer', 'Encoder'],
      explanation: 'Software or creator labels may reveal which tools, firmware or devices processed this file.',
      recommendation: 'Review these labels and remove unnecessary tool or version details from a sharing copy.'
    },
    {
      title: 'Comments', fields: ['Comment', 'Comments'],
      explanation: 'Saved comments may contain personal details or notes that were not intended for others.',
      recommendation: 'Read the comments and remove private notes from a copy before sharing.'
    }
  ];
  const items = groups.flatMap((group) => {
    const fields = group.fields.filter((field) => detected.has(field));
    return fields.length ? [{ ...group, fields }] : [];
  });
  // Future or unmapped alerts stay visible without speculative interpretation.
  const covered = new Set(items.flatMap((item) => item.fields));
  const otherFields = [...new Set(findings.filter((finding) => hasSummaryValue(finding.value) && !covered.has(finding.field)).map((finding) => finding.field))];
  if (otherFields.length) items.push({
    title: 'Other privacy signals', fields: otherFields,
    explanation: 'The privacy checks flagged additional metadata for review.',
    recommendation: 'Review the flagged values below before sharing this file.'
  });
  return items;
}

function renderPrivacySummary(metadata, findings) {
  const items = buildPrivacySummary(metadata, findings);
  const container = element('privacy-summary-items');
  container.replaceChildren();
  element('privacy-summary-intro').textContent = items.length
    ? 'This file includes information worth reviewing before you share it.'
    : 'No sensitive metadata was detected in the available results. This does not guarantee that the file is completely private. Review its contents and any information this tool may not detect before sharing.';
  items.forEach((item) => {
    const card = textNode('article', '', 'privacy-summary-item');
    card.append(
      textNode('h4', item.title),
      textNode('p', item.explanation),
      textNode('p', `Detected fields: ${item.fields.join(', ')}`, 'privacy-summary-evidence'),
      textNode('p', item.recommendation, 'privacy-summary-recommendation')
    );
    container.append(card);
  });
}

function renderResults(report) {
  const { file, metadata, findings } = report;
  element('result-name').textContent = file.name;
  element('result-type').textContent = (file.extension || '').replace('.', '').toUpperCase() || 'FILE';
  element('result-mime').textContent = file.mime_type || 'Unknown type';
  element('result-size').textContent = formatSize(file.size_bytes);
  const rows = element('metadata-body');
  rows.replaceChildren();
  const entries = Object.entries(metadata);
  entries.forEach(([field, value]) => {
    const row = document.createElement('tr');
    row.append(textNode('td', field), textNode('td', formatValue(value)));
    rows.append(row);
  });
  element('metadata-count').textContent = `${entries.length} fields`;
  element('metadata-empty').hidden = entries.length > 0;
  const list = element('findings-list');
  list.replaceChildren();
  findings.forEach((finding) => {
    const item = textNode('article', '', 'finding');
    item.append(textNode('span', finding.field, 'finding-field'), textNode('p', formatValue(finding.value), 'finding-value'), textNode('p', finding.description, 'finding-description'));
    list.append(item);
  });
  element('findings-count').textContent = `${findings.length} signals`;
  element('findings-empty').hidden = findings.length > 0;
  renderLocation(metadata, findings);
  renderPrivacySummary(metadata, findings);
  element('upload-panel').hidden = true;
  element('how-it-works').hidden = true;
  element('results').hidden = false;
  element('results-heading').focus();
}

function setBusy(value) {
  busy = value;
  fileInput.disabled = value;
  analyzeButton.disabled = value || !selectedFile;
  element('progress').hidden = !value;
  form.setAttribute('aria-busy', String(value));
}

const HTTP_ERRORS = {
  400: 'The upload could not be read. Select a non-empty file and try again.',
  413: 'The upload exceeds the size limit. Choose a file smaller than 20 MiB.',
  415: 'This file format is not supported. Check the compatible formats.',
  422: 'This file could not be validated. It may be damaged, mislabeled, encrypted or exceed safety limits.',
  500: 'The analysis could not be completed. Please try again or choose another file.'
};

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !selectedFile) return;
  showError('');
  setBusy(true);
  const body = new FormData();
  body.append('file', selectedFile);
  try {
    const response = await fetch('/api/inspect', { method: 'POST', body, cache: 'no-store' });
    if (!response.ok) {
      showError(HTTP_ERRORS[response.status] || 'The analysis could not be completed. Please try again.');
      return;
    }
    renderResults(await response.json());
    inspectedFile = selectedFile;
    clearCleanResult();
    element('remove-button').disabled = !new Set(['jpg', 'jpeg', 'png', 'pdf', 'docx', 'xlsx', 'pptx', 'mp3']).has(inspectedFile.name.split('.').pop().toLowerCase());
    if (element('remove-button').disabled) element('clean-status').textContent = 'Metadata removal is not supported for this format. MP4 and MOV cleaning is disabled.';
    resetSelection();
  } catch {
    showError('Unable to complete the request. Check that the local application is running and try again.');
  } finally {
    setBusy(false);
  }
});

element('reset-button').addEventListener('click', () => {
  if (cleaning) return;
  inspectedFile = null;
  clearCleanResult();
  resetSelection();
  showError('');
  ['metadata-body', 'findings-list', 'gps-values', 'privacy-summary-items'].forEach((id) => element(id).replaceChildren());
  element('privacy-summary-intro').textContent = '';
  ['result-name', 'result-type', 'result-mime', 'result-size'].forEach((id) => { element(id).textContent = ''; });
  element('results').hidden = true;
  element('gps-panel').hidden = true;
  element('upload-panel').hidden = false;
  element('how-it-works').hidden = false;
  fileInput.focus();
});


function clearCleanResult() {
  if (cleanUrl) URL.revokeObjectURL(cleanUrl);
  cleanUrl = null;
  element('download-button').hidden = true;
  element('download-button').removeAttribute('href');
  element('clean-report').replaceChildren();
  element('clean-report').hidden = true;
  element('clean-status').textContent = '';
}

element('remove-button').addEventListener('click', async () => {
  if (cleaning || !inspectedFile || element('remove-button').disabled) return;
  cleaning = true;
  clearCleanResult();
  element('remove-button').disabled = true;
  element('reset-button').disabled = true;
  element('clean-status').textContent = 'Removing supported metadata and verifying the copy…';
  const body = new FormData();
  body.append('file', inspectedFile);
  try {
    const response = await fetch('/api/clean', { method: 'POST', body, cache: 'no-store' });
    const result = await response.json();
    if (!response.ok) {
      element('clean-status').textContent = response.status === 422 ? result.detail : (HTTP_ERRORS[response.status] || 'The file could not be cleaned.');
      return;
    }
    const bytes = Uint8Array.from(atob(result.data), (char) => char.charCodeAt(0));
    cleanUrl = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
    const link = element('download-button');
    link.href = cleanUrl;
    link.download = result.name;
    link.hidden = false;
    const report = element('clean-report');
    report.append(
      textNode('p', `Removed detected fields: ${result.report.removed_fields.join(', ') || 'None'}`),
      textNode('p', `Changed detected fields: ${result.report.changed_fields.join(', ') || 'None'}`),
      textNode('p', `Still detected: ${Object.keys(result.report.remaining_metadata).join(', ') || 'None by the current extractor'}`),
      textNode('p', `Remaining privacy signals: ${result.report.remaining_findings.map((finding) => finding.field).join(', ') || 'None by the current rules'}`)
    );
    result.report.operations.forEach((operation) => report.append(textNode('p', operation)));
    result.report.warnings.forEach((warning) => report.append(textNode('p', warning)));
    report.append(textNode('p', result.report.notice));
    report.hidden = false;
    element('clean-status').textContent = 'Copy verified. Review what remains before downloading and sharing.';
  } catch {
    clearCleanResult();
    element('clean-status').textContent = 'The file could not be cleaned. Check that the local application is running and try again.';
  } finally {
    cleaning = false;
    element('remove-button').disabled = false;
    element('reset-button').disabled = false;
  }
});
window.addEventListener('pagehide', () => {
  if (cleanUrl) URL.revokeObjectURL(cleanUrl);
  cleanUrl = null;
  inspectedFile = null;
});
