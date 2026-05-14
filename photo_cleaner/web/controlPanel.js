const logsNode = document.getElementById("logs");
const fullRunButtonNode = document.getElementById("fullRunButton");
const orientationRunButtonNode = document.getElementById("orientationRunButton");
const applyButtonNode = document.getElementById("applyButton");
const undoApplyButtonNode = document.getElementById("undoApplyButton");
const clearDbButtonNode = document.getElementById("clearDbButton");
const saveConfigButtonNode = document.getElementById("saveConfigButton");
const reloadConfigButtonNode = document.getElementById("reloadConfigButton");
const openDuplicatesReportButtonNode = document.getElementById("openDuplicatesReportButton");
const openOrientationReportButtonNode = document.getElementById("openOrientationReportButton");
const trustedCameraModelsNode = document.getElementById("trustedCameraModels");
const usedCameraModelsNode = document.getElementById("usedCameraModels");
const extensionCountsNode = document.getElementById("extensionCounts");
const dupExactGroupsCountNode = document.getElementById("dupExactGroupsCount");
const dupExactFilesCountNode = document.getElementById("dupExactFilesCount");
const dupSimilarGroupsCountNode = document.getElementById("dupSimilarGroupsCount");
const dupSimilarFilesCountNode = document.getElementById("dupSimilarFilesCount");
const dupConfirmedCountNode = document.getElementById("dupConfirmedCount");
const dupPendingCountNode = document.getElementById("dupPendingCount");
const oriCandidatesCountNode = document.getElementById("oriCandidatesCount");
const oriAutoCountNode = document.getElementById("oriAutoCount");
const oriManualCountNode = document.getElementById("oriManualCount");
const oriResolvedCountNode = document.getElementById("oriResolvedCount");
const oriPendingCountNode = document.getElementById("oriPendingCount");
const cfgArchiveRootNode = document.getElementById("cfgArchiveRoot");
const cfgTrustedCamerasNode = document.getElementById("cfgTrustedCameras");
const cfgExcludedPrefixesNode = document.getElementById("cfgExcludedPrefixes");
const kpiTotalFilesNode = document.getElementById("kpiTotalFiles");
const kpiOrientationResolvedNode = document.getElementById("kpiOrientationResolved");
const kpiDuplicateConfirmedNode = document.getElementById("kpiDuplicateConfirmed");
const kpiManualReviewNode = document.getElementById("kpiManualReview");
const orientationProgressFillNode = document.getElementById("orientationProgressFill");
const duplicateProgressFillNode = document.getElementById("duplicateProgressFill");
const orientationBadgeNode = document.getElementById("orientationBadge");
const duplicateBadgeNode = document.getElementById("duplicateBadge");
const manualBadgeNode = document.getElementById("manualBadge");

let isRunning = false;
let logOffset = 0;
let hasCompletedFullRun = false;

function updateCommandButtonsState() {
  const allButtons = Array.from(document.querySelectorAll("button"));
  for (const buttonNode of allButtons) {
    if (!(buttonNode instanceof HTMLButtonElement)) {
      continue;
    }

    const isFullRunButton = fullRunButtonNode !== null && buttonNode === fullRunButtonNode;
    const isClearDbButton = clearDbButtonNode !== null && buttonNode === clearDbButtonNode;
    const isSaveConfigButton = saveConfigButtonNode !== null && buttonNode === saveConfigButtonNode;
    const isReloadConfigButton = reloadConfigButtonNode !== null && buttonNode === reloadConfigButtonNode;

    if (isClearDbButton || isSaveConfigButton || isReloadConfigButton) {
      buttonNode.disabled = false;
      continue;
    }

    if (isRunning) {
      buttonNode.disabled = true;
      continue;
    }

    if (!hasCompletedFullRun) {
      if (isFullRunButton) {
        buttonNode.disabled = false;
      } else if (orientationRunButtonNode !== null && buttonNode === orientationRunButtonNode) {
        buttonNode.disabled = true;
      } else {
        buttonNode.disabled = true;
      }
      continue;
    }

    buttonNode.disabled = false;
  }
}

function appendLogs(text) {
  logsNode.textContent += "\n\n" + text;
  logsNode.scrollTop = logsNode.scrollHeight;
}

function openReport(url) {
  window.open(url, "_blank");
}

function openReportWhenReady(url) {
  const popupWindow = window.open(url, "_blank");
  if (popupWindow && !popupWindow.closed) {
    return;
  }
  appendLogs(
    "Браузер заблокировал открытие новой вкладки с отчетом. " +
    "Разрешите pop-up для панели и откройте отчет кнопкой вручную."
  );
}

function renderSimpleList(listNode, values) {
  if (!listNode) {
    return;
  }
  listNode.innerHTML = "";
  if (!values || values.length === 0) {
    const item = document.createElement("li");
    item.textContent = "(пусто)";
    listNode.appendChild(item);
    return;
  }
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = String(value);
    listNode.appendChild(item);
  }
}

function renderCountList(listNode, values, keyName) {
  if (!listNode) {
    return;
  }
  listNode.innerHTML = "";
  if (!values || values.length === 0) {
    const item = document.createElement("li");
    item.textContent = "(пусто)";
    listNode.appendChild(item);
    return;
  }
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = String(value[keyName]) + ": " + String(value.count);
    listNode.appendChild(item);
  }
}

function formatPercent(part, total) {
  if (!total || total <= 0) {
    return 0;
  }
  return Math.round((part / total) * 100);
}

function setBadge(node, level, text) {
  node.className = "badge " + level;
  node.textContent = text;
}

function renderKpi(payload) {
  const totalFiles = Number(payload.totalFiles || 0);
  const orientationResolved = Number(payload.orientationResolvedCount || 0);
  const orientationPending = Number(payload.orientationPendingCount || 0);
  const duplicateConfirmed = Number(payload.duplicateConfirmedCount || 0);
  const duplicatePending = Number(payload.duplicatePendingCount || 0);
  const orientationAuto = Number(payload.orientationSuggestedAutoCount || 0);
  const orientationManual = Number(payload.orientationSuggestedManualCount || 0);

  const orientationTotal = orientationResolved + orientationPending;
  const duplicateTotal = duplicateConfirmed + duplicatePending;
  const suggestedTotal = orientationAuto + orientationManual;

  const orientationResolvedPercent = formatPercent(orientationResolved, orientationTotal);
  const duplicateConfirmedPercent = formatPercent(duplicateConfirmed, duplicateTotal);
  const manualReviewPercent = formatPercent(orientationManual, suggestedTotal);

  kpiTotalFilesNode.textContent = String(totalFiles);
  kpiOrientationResolvedNode.textContent = String(orientationResolvedPercent) + "%";
  kpiDuplicateConfirmedNode.textContent = String(duplicateConfirmedPercent) + "%";
  kpiManualReviewNode.textContent = String(manualReviewPercent) + "%";
  orientationProgressFillNode.style.width = String(orientationResolvedPercent) + "%";
  duplicateProgressFillNode.style.width = String(duplicateConfirmedPercent) + "%";

  if (orientationResolvedPercent >= 80) {
    setBadge(orientationBadgeNode, "ok", "orientation ok");
  } else if (orientationResolvedPercent >= 40) {
    setBadge(orientationBadgeNode, "warn", "orientation in progress");
  } else {
    setBadge(orientationBadgeNode, "danger", "orientation attention");
  }

  if (duplicateConfirmedPercent >= 80) {
    setBadge(duplicateBadgeNode, "ok", "duplicates ok");
  } else if (duplicateConfirmedPercent >= 40) {
    setBadge(duplicateBadgeNode, "warn", "duplicates in progress");
  } else {
    setBadge(duplicateBadgeNode, "danger", "duplicates attention");
  }

  if (manualReviewPercent <= 20) {
    setBadge(manualBadgeNode, "ok", "manual review low");
  } else if (manualReviewPercent <= 45) {
    setBadge(manualBadgeNode, "warn", "manual review medium");
  } else {
    setBadge(manualBadgeNode, "danger", "manual review high");
  }
}

async function loadSummary() {
  try {
    const summaryUrl = "/api/summary?ts=" + String(Date.now());
    const response = await fetch(summaryUrl, {
      method: "GET",
      cache: "no-store",
    });
    const payload = await response.json();
    renderSimpleList(trustedCameraModelsNode, payload.trustedCameraModels || []);
    renderCountList(usedCameraModelsNode, payload.usedCameraModelCounts || [], "cameraModel");
    renderCountList(extensionCountsNode, payload.extensionCounts || [], "extension");
    dupExactGroupsCountNode.textContent = String(payload.exactDuplicateGroupsCount || 0);
    dupExactFilesCountNode.textContent = String(payload.exactDuplicateFilesCount || 0);
    dupSimilarGroupsCountNode.textContent = String(payload.similarDuplicateGroupsCount || 0);
    dupSimilarFilesCountNode.textContent = String(payload.similarDuplicateFilesCount || 0);
    dupConfirmedCountNode.textContent = String(payload.duplicateConfirmedCount || 0);
    dupPendingCountNode.textContent = String(payload.duplicatePendingCount || 0);
    oriCandidatesCountNode.textContent = String(payload.orientationCandidatesCount || 0);
    oriAutoCountNode.textContent = String(payload.orientationSuggestedAutoCount || 0);
    oriManualCountNode.textContent = String(payload.orientationSuggestedManualCount || 0);
    oriResolvedCountNode.textContent = String(payload.orientationResolvedCount || 0);
    oriPendingCountNode.textContent = String(payload.orientationPendingCount || 0);
    renderKpi(payload);
  } catch (error) {
    appendLogs("Ошибка загрузки сводки: " + String(error));
  }
}

async function refreshHeaderData() {
  await loadSummary();
  await loadConfigEditor();
}

function splitLines(textValue) {
  const normalizedText = String(textValue || "").replace(/\r/g, "");
  const lines = normalizedText.split("\n");
  const values = [];
  for (const line of lines) {
    const text = line.trim();
    if (text) {
      values.push(text);
    }
  }
  return values;
}

async function loadConfigEditor() {
  try {
    const response = await fetch("/api/config", { method: "GET" });
    const payload = await response.json();
    cfgArchiveRootNode.value = String(payload.archiveRoot || "");
    cfgTrustedCamerasNode.value = (payload.trustedCameraModels || []).join("\n");
    cfgExcludedPrefixesNode.value = (payload.excludedPathPrefixes || []).join("\n");
  } catch (error) {
    appendLogs("Ошибка загрузки config: " + String(error));
  }
}

async function saveConfig() {
  const payload = {
    archiveRoot: cfgArchiveRootNode.value,
    trustedCameraModels: splitLines(cfgTrustedCamerasNode.value),
    excludedPathPrefixes: splitLines(cfgExcludedPrefixesNode.value),
  };
  try {
    const response = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (result.success) {
      appendLogs("config.yaml обновлен");
      await loadConfigEditor();
      await loadSummary();
    } else {
      appendLogs("Ошибка сохранения config: " + String(result.message || "unknown"));
    }
  } catch (error) {
    appendLogs("Ошибка сохранения config: " + String(error));
  }
}

async function runCommand(command) {
  if (isRunning) {
    appendLogs("Команда уже выполняется, дождитесь завершения.");
    return;
  }
  let options = {};
  if (command === "apply") {
    const applyOptions = await buildApplyOptionsOrCancel();
    if (applyOptions === null) {
      appendLogs(">>> отменено: apply");
      return;
    }
    options = applyOptions;
  }
  isRunning = true;
  updateCommandButtonsState();
  logOffset = 0;
  appendLogs(">>> start: " + command);
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, options }),
    });
    const payload = await response.json();
    if (!payload.started) {
      appendLogs(payload.logs || "Не удалось запустить команду.");
      return;
    }
    await pollLogsUntilDone(command);
  } catch (error) {
    appendLogs("Ошибка: " + String(error));
  } finally {
    appendLogs(">>> done: " + command);
    isRunning = false;
    updateCommandButtonsState();
  }
}

async function buildApplyOptionsOrCancel() {
  let ret = {
    applyPendingDuplicates: false,
    applyPendingOrientation: false,
  };

  let summaryPayload = null;
  try {
    const summaryUrl = "/api/summary?ts=" + String(Date.now());
    const response = await fetch(summaryUrl, {
      method: "GET",
      cache: "no-store",
    });
    summaryPayload = await response.json();
  } catch (error) {
    appendLogs("Не удалось прочитать summary перед apply: " + String(error));
    ret = null;
    return ret;
  }

  const duplicatePendingCount = Number(summaryPayload.duplicatePendingCount || 0);
  const orientationPendingCount = Number(summaryPayload.orientationPendingCount || 0);

  if (duplicatePendingCount > 0) {
    const confirmedDuplicates = window.confirm(
      "Есть неподтвержденные дубли: " + String(duplicatePendingCount) + ".\n\n" +
      "Согласны, что при apply будут обработаны ВСЕ дубли, включая неподтвержденные?"
    );
    if (!confirmedDuplicates) {
      ret = null;
      return ret;
    }
    ret.applyPendingDuplicates = true;
  }

  if (orientationPendingCount > 0) {
    const confirmedOrientation = window.confirm(
      "Есть неподтвержденные кандидаты ориентации: " + String(orientationPendingCount) + ".\n\n" +
      "Согласны, что при apply для неподтвержденных будет применено решение машины (suggested)?"
    );
    if (!confirmedOrientation) {
      ret = null;
      return ret;
    }
    ret.applyPendingOrientation = true;
  }

  return ret;
}

function runDangerousCommand(command, confirmMessage) {
  const confirmText = String(confirmMessage || "Подтвердите выполнение опасной команды.");
  if (!window.confirm(confirmText)) {
    return;
  }
  runCommand(command);
}

async function pollLogsUntilDone(command) {
  let done = false;
  while (!done) {
    const response = await fetch("/api/status?offset=" + String(logOffset), { method: "GET" });
    const payload = await response.json();
    if (payload.logs) {
      appendLogs(payload.logs);
    }
    logOffset = Number(payload.nextOffset || logOffset);
    if (payload.finished) {
      done = true;
      if (command === "full-run" && payload.success) {
        hasCompletedFullRun = true;
      }
      if (command === "clear-db" && payload.success) {
        hasCompletedFullRun = false;
      }
      if (payload.reportUrl) {
        appendLogs(">>> opening report: " + payload.reportUrl);
        openReportWhenReady(payload.reportUrl);
      }
      await refreshHeaderData();
      await new Promise((resolve) => setTimeout(resolve, 250));
      await refreshHeaderData();
    } else {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
}

updateCommandButtonsState();
refreshHeaderData();

window.addEventListener("focus", () => {
  refreshHeaderData();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshHeaderData();
  }
});
