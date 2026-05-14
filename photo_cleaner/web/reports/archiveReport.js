const archivePhotosGridNode = document.getElementById("archivePhotosGrid");
const archivePrevButtonNode = document.getElementById("archivePrevButton");
const archiveNextButtonNode = document.getElementById("archiveNextButton");
const archivePageInfoNode = document.getElementById("archivePageInfo");

let archivePage = 1;
const archivePageSize = 20;
let archiveTotalPages = 0;

function formatArchiveSize(in_sizeValue) {
  const sizeValue = Number(in_sizeValue || 0);
  let ret = String(sizeValue) + " B";
  if (sizeValue >= 1024 * 1024) {
    ret = (sizeValue / (1024 * 1024)).toFixed(2) + " MB";
  } else if (sizeValue >= 1024) {
    ret = (sizeValue / 1024).toFixed(1) + " KB";
  }
  return ret;
}

function formatArchiveMtime(in_mtimeValue) {
  const mtimeValue = Number(in_mtimeValue || 0);
  const dateValue = new Date(mtimeValue * 1000);
  let ret = "-";
  if (!Number.isNaN(dateValue.getTime())) {
    ret = dateValue.toLocaleString();
  }
  return ret;
}

function buildArchiveMetaLine(in_item) {
  const extensionValue = String(in_item.extension || "(unknown)");
  const sizeText = formatArchiveSize(in_item.size);
  const cameraValue = String(in_item.cameraModel || "(unknown)");
  const dimensionsText = String(in_item.width || 0) + "x" + String(in_item.height || 0);
  const mtimeText = formatArchiveMtime(in_item.mtime);
  const ret = `ext: ${extensionValue} | size: ${sizeText} | camera: ${cameraValue} | ${dimensionsText} | mtime: ${mtimeText}`;
  return ret;
}

function renderArchiveItems(in_items) {
  archivePhotosGridNode.innerHTML = "";
  if (!in_items || in_items.length === 0) {
    const emptyNode = document.createElement("div");
    emptyNode.className = "card";
    emptyNode.textContent = "Фото не найдены. Сначала выполните скан архива.";
    archivePhotosGridNode.appendChild(emptyNode);
    return;
  }

  for (const item of in_items) {
    const cardNode = document.createElement("div");
    cardNode.className = "card archiveCard";

    const titleNode = document.createElement("div");
    titleNode.className = "archivePath";
    titleNode.textContent = String(item.relativePath || "");
    cardNode.appendChild(titleNode);

    const previewBoxNode = document.createElement("div");
    previewBoxNode.className = "archivePreview";
    const thumbnailUrl = item.thumbnailUrl;
    if (thumbnailUrl) {
      const imageNode = document.createElement("img");
      imageNode.className = "archiveImage";
      imageNode.src = String(thumbnailUrl);
      imageNode.alt = String(item.relativePath || "");
      previewBoxNode.appendChild(imageNode);
    } else {
      const rawNode = document.createElement("div");
      rawNode.className = "rawBox";
      rawNode.textContent = "RAW / no preview";
      previewBoxNode.appendChild(rawNode);
    }
    cardNode.appendChild(previewBoxNode);

    const metaNode = document.createElement("div");
    metaNode.className = "meta archiveMeta";
    metaNode.textContent = buildArchiveMetaLine(item);
    cardNode.appendChild(metaNode);

    const idNode = document.createElement("div");
    idNode.className = "meta";
    idNode.textContent = "id: " + String(item.id || "");
    cardNode.appendChild(idNode);

    archivePhotosGridNode.appendChild(cardNode);
  }
}

function updateArchivePagination(in_total) {
  const totalValue = Number(in_total || 0);
  const currentPage = archivePage;
  const totalPages = archiveTotalPages;

  archivePrevButtonNode.disabled = currentPage <= 1;
  archiveNextButtonNode.disabled = currentPage >= totalPages || totalPages === 0;
  archivePageInfoNode.textContent = `Страница ${currentPage} из ${Math.max(1, totalPages)} | Всего фото: ${totalValue}`;
}

async function loadArchivePage(in_page) {
  let pageValue = Number(in_page || 1);
  if (!Number.isFinite(pageValue) || pageValue < 1) {
    pageValue = 1;
  }

  const url = `/api/archive/photos?page=${pageValue}&pageSize=${archivePageSize}&ts=${Date.now()}`;
  const response = await fetch(url, {
    method: "GET",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("failed to load archive page");
  }
  const payload = await response.json();
  archivePage = Number(payload.page || pageValue);
  archiveTotalPages = Number(payload.totalPages || 0);
  renderArchiveItems(payload.items || []);
  updateArchivePagination(Number(payload.total || 0));
}

async function safeLoadArchivePage(in_page) {
  try {
    await loadArchivePage(in_page);
  } catch (_error) {
    archivePhotosGridNode.innerHTML = "";
    const errorNode = document.createElement("div");
    errorNode.className = "card";
    errorNode.textContent = "Не удалось загрузить страницу обзора архива.";
    archivePhotosGridNode.appendChild(errorNode);
  }
}

archivePrevButtonNode.addEventListener("click", () => {
  safeLoadArchivePage(archivePage - 1);
});

archiveNextButtonNode.addEventListener("click", () => {
  safeLoadArchivePage(archivePage + 1);
});

safeLoadArchivePage(1);
