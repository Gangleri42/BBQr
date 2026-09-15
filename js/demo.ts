// code only for the demo page, not part of the library

import { detectFileType, renderQRImage, splitQRs } from './src/main';

const resultEl = document.querySelector<HTMLDivElement>('#result')!;
const inputEl = document.querySelector<HTMLTextAreaElement>('#text-input')!;
const parityEl = document.querySelector<HTMLInputElement>('#parity')!;

// remembered so a change to the parity count can redo the last split
let lastInput: File | string | undefined;

function clearPrevious() {
  const existingImgs = resultEl.querySelectorAll('img');

  existingImgs.forEach((img) => {
    // remove references to any old images
    URL.revokeObjectURL(img.src);
  });

  resultEl.innerHTML = '';
}

let busy = false;

async function handleFileOrTextInput(input: File | string) {
  if (busy) {
    return;
  }

  busy = true;
  lastInput = input;

  try {
    clearPrevious();

    let resultMsg = '';

    const { raw, fileType } = await detectFileType(input);

    resultMsg += `Detected file type: <strong>${fileType}</strong><br>`;

    const parity = Math.max(0, Math.min(254, Number(parityEl.value) || 0));

    const { parts, version } = splitQRs(raw, fileType, { encoding: 'Z', parity });

    const imgBuf = await renderQRImage(parts, version);

    // the header's count is the number of data parts; the rest are parity
    const numData = parseInt(parts[0].slice(4, 6), 36);

    if (parts.length === 1) {
      resultMsg += `A single QR version ${version} will be needed.`;
    } else if (parts.length > numData) {
      resultMsg += `Need ${parts.length} QRs of version ${version}: `;
      resultMsg += `${numData} data + ${parts.length - numData} parity, any ${numData} recover the data.`;
    } else {
      resultMsg += `Need ${parts.length} QRs of version ${version}.`;
    }

    resultEl.innerHTML = `<p>${resultMsg}</p>`;

    const url = URL.createObjectURL(new Blob([imgBuf], { type: 'image/png' }));

    resultEl.innerHTML += `<img src="${url}" alt="QR codes" />`;
  } finally {
    busy = false;
  }
}

document.addEventListener('dragover', (e) => {
  // prevent browser from opening the file when dropped
  e.preventDefault();
});

document.addEventListener('drop', (e) => {
  e.preventDefault();

  if (!e.dataTransfer) {
    return;
  }

  const files: File[] = [];

  for (const item of e.dataTransfer.items) {
    if (item.kind === 'file') {
      const file = item.getAsFile();

      if (file) {
        files.push(file);
      }
    }
  }

  if (files.length > 1) {
    throw new Error('Only one file at a time, please.');
  } else if (files.length === 1) {
    inputEl.value = '';
    handleFileOrTextInput(files[0]);
  }
});

// redo the last split when the parity count changes
parityEl.addEventListener('change', () => {
  if (lastInput !== undefined) {
    handleFileOrTextInput(lastInput);
  }
});

// detect paste in textarea
inputEl.addEventListener('paste', (e) => {
  const text = e.clipboardData?.getData('text');

  if (text) {
    handleFileOrTextInput(text);
  }
});
