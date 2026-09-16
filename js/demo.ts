// code only for the demo page, not part of the library

import { detectFileType, renderQRImage, splitQRs } from './src/main';
import type { SplitResult } from './src/main';

const resultEl = document.querySelector<HTMLDivElement>('#result')!;
const inputEl = document.querySelector<HTMLTextAreaElement>('#text-input')!;
const neededEl = document.querySelector<HTMLInputElement>('#needed')!;
const totalEl = document.querySelector<HTMLInputElement>('#total')!;
const hintEl = document.querySelector<HTMLElement>('#split-hint')!;
const initialHint = hintEl.textContent;

// remembered so a change to the split can redo the last input
let lastInput: File | string | undefined;

// what was asked for; the inputs show what was made, which can be more
const wanted = { needed: 1, total: 1 };

function clearPrevious() {
  const existingImgs = resultEl.querySelectorAll('img');

  existingImgs.forEach((img) => {
    // remove references to any old images
    URL.revokeObjectURL(img.src);
  });

  resultEl.innerHTML = '';
}

// the header's count: the number of data parts, and how many parts are needed
function numData(parts: string[]) {
  return parseInt(parts[0].slice(4, 6), 36);
}

// a whole number in the library's range, whatever was typed into a number input
function readCount(el: HTMLInputElement) {
  return Math.min(1295, Math.max(1, Math.floor(Number(el.value)) || 1));
}

// splitQRs with the demo's fixed encoding and a reason in place of 'Cannot make it fit';
// every QR version is allowed, so a payload that fits one QR can still go onto several
function trySplit(raw: Uint8Array, fileType: string, parity: number, minSplit: number, cannotFit: string) {
  try {
    return splitQRs(raw, fileType, { encoding: 'Z', parity, minSplit, minVersion: 1 });
  } catch (err) {
    if (err instanceof Error && err.message === 'Cannot make it fit') {
      throw new Error(cannotFit);
    }

    throw err;
  }
}

/**
 * Splits so that any `needed` of `total` QR codes recover the data.
 *
 * - `needed` is raised to the fewest QR codes the data takes, which can be one more
 *   with parity than without, and further when no QR version splits the data into
 *   exactly that many
 * - `total` stays as asked for, as long as that leaves at least one parity part
 * - `floor` and `parityFloor` are the fewest QR codes without and with parity
 */
export function planSplit(raw: Uint8Array, fileType: string, needed: number, total: number) {
  const tooMany = (count: number) => `this data is too small to split into ${count} QR codes`;

  let result: SplitResult = trySplit(raw, fileType, 0, 1, 'this data does not fit into 1295 QR codes');
  const floor = numData(result.parts);

  if (total <= needed) {
    if (needed > floor) {
      result = trySplit(raw, fileType, 0, needed, tooMany(needed));
    }

    return { ...result, floor, parityFloor: floor };
  }

  // parity parts are a symbol group longer, so the data may need one more QR code
  const single = 'this data fits in a single QR code, which parity cannot protect';
  const parityFloor = numData(trySplit(raw, fileType, 1, 2, single).parts);

  const dataCount = Math.max(needed, parityFloor);
  const parityFor = (count: number) => Math.min(254, Math.max(1, total - count));

  // ask for the smallest split that takes parity unless more parts are wanted: splitQRs
  // applies minSplit before it makes room for parity, so asking for parityFloor itself
  // can fail when only that room made it reachable
  const minSplit = Math.max(needed, 2);

  result = trySplit(raw, fileType, parityFor(dataCount), minSplit, tooMany(needed));

  // no QR version gives exactly dataCount: keep the total for the count that was made
  const made = numData(result.parts);

  if (parityFor(made) !== parityFor(dataCount)) {
    result = trySplit(raw, fileType, parityFor(made), minSplit, tooMany(needed));
  }

  return { ...result, floor, parityFloor };
}

async function splitAndShow(input: File | string) {
  if (input !== lastInput) {
    // new data: as few QR codes as it needs, keeping the total that was asked for
    wanted.needed = 1;
    neededEl.value = '1';
  }

  lastInput = input;

  clearPrevious();

  let resultMsg = '';

  const { raw, fileType } = await detectFileType(input);

  resultMsg += `Detected file type: <strong>${fileType}</strong><br>`;

  const { needed, total } = wanted;

  let plan: ReturnType<typeof planSplit>;

  try {
    plan = planSplit(raw, fileType, needed, total);
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);

    resultEl.innerHTML = `<p>${resultMsg}Cannot split into ${needed} of ${total}: ${reason}.</p>`;
    hintEl.textContent = initialHint;

    // nothing was made, so the inputs show what was asked for
    neededEl.value = String(needed);
    totalEl.value = String(total);
    return;
  }

  const { parts, version, floor, parityFloor } = plan;
  const dataCount = numData(parts);
  const parityCount = parts.length - dataCount;
  const least = parityCount ? parityFloor : floor;

  // the inputs show what was done, which may be more than was asked for
  neededEl.value = String(dataCount);
  neededEl.min = String(least);
  totalEl.value = String(parts.length);
  totalEl.min = String(dataCount);

  let hint =
    parityCount && parityFloor !== floor
      ? `With parity the smallest split is ${parityFloor} QR codes, ${floor} without.`
      : `This data needs at least ${floor} QR code${floor === 1 ? '' : 's'}.`;

  if (dataCount > Math.max(needed, least)) {
    hint += ` No QR version splits it into exactly ${needed}.`;
  }

  hintEl.textContent = hint;

  const imgBuf = await renderQRImage(parts, version);

  if (parts.length === 1) {
    resultMsg += `A single QR version ${version} will be needed.`;
  } else if (parityCount) {
    resultMsg += `Need ${parts.length} QRs of version ${version}: `;
    resultMsg += `${dataCount} data + ${parityCount} parity, any ${dataCount} recover the data.`;
  } else {
    resultMsg += `Need ${parts.length} QRs of version ${version}.`;
  }

  resultEl.innerHTML = `<p>${resultMsg}</p>`;

  const url = URL.createObjectURL(new Blob([imgBuf], { type: 'image/png' }));

  resultEl.innerHTML += `<img src="${url}" alt="QR codes" />`;
}

let busy = false;

// input that arrived while busy, split once the current one is shown
let pending: File | string | undefined;

async function handleFileOrTextInput(input: File | string) {
  if (busy) {
    pending = input;
    return;
  }

  busy = true;

  try {
    let next: File | string | undefined = input;

    while (next !== undefined) {
      await splitAndShow(next);

      next = pending;
      pending = undefined;
    }
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

// redo the last split when the m of n changes
function resplit() {
  if (lastInput !== undefined) {
    handleFileOrTextInput(lastInput);
  }
}

neededEl.addEventListener('change', () => {
  wanted.needed = readCount(neededEl);
  resplit();
});

totalEl.addEventListener('change', () => {
  wanted.total = readCount(totalEl);
  resplit();
});

// detect paste in textarea
inputEl.addEventListener('paste', (e) => {
  const text = e.clipboardData?.getData('text');

  if (text) {
    handleFileOrTextInput(text);
  }
});
