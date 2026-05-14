const pcReportConfigNode = document.getElementById("pc-report-config");
const pcActionsPath = pcReportConfigNode ? String(pcReportConfigNode.dataset.actionsPath || "../actions.json") : "../actions.json";
const pcThumbsSubdir = pcReportConfigNode ? String(pcReportConfigNode.dataset.thumbsSubdir || "orientation_ml") : "orientation_ml";
const pcThumbsBasePath = pcReportConfigNode ? String(pcReportConfigNode.dataset.thumbsBasePath || "/workspace/thumbs") : "/workspace/thumbs";
const pcActionsStateNode = document.getElementById("pc-actions-state");
const pcActionsState = pcActionsStateNode ? JSON.parse(pcActionsStateNode.textContent || "{}") : {};
let pcIsSaving = false;
let pcHasPendingSave = false;
let pcPendingPayload = null;

function pcUpdateInfo(in_text) {
  const node = document.getElementById("pcActionsInfo");
  if (node) {
    node.textContent = in_text;
  }
}

async function pcPersistActionsNow(
  in_payload,
) {
  pcPendingPayload = in_payload;
  if (pcIsSaving) {
    pcHasPendingSave = true;
    return;
  }
  pcIsSaving = true;
  try {
    const payloadToSend = pcPendingPayload;
    pcPendingPayload = null;
    const out_response = await fetch("/api/actions?scope=orientation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadToSend || {}),
    });
    if (out_response.ok) {
      pcUpdateInfo("actions.json сохранен");
    } else {
      pcUpdateInfo("не удалось сохранить actions.json");
    }
  } catch (_error) {
    pcUpdateInfo("ошибка сохранения actions.json");
  } finally {
    pcIsSaving = false;
    if (pcHasPendingSave) {
      pcHasPendingSave = false;
      pcPersistActionsNow();
    }
  }
}

function pcOrientationApplySuggested(in_photoId, in_rotation, in_action) {
  pcOrientationSet(in_photoId, in_rotation, in_action, false);
}

function pcNormalizeRotation(in_rotation) {
  let ret = null;
  if (in_rotation === null || in_rotation === undefined) {
    return ret;
  }
  const parsed = Number(in_rotation);
  if (Number.isFinite(parsed)) {
    ret = parsed;
  }
  return ret;
}

function pcNormalizeAction(in_action) {
  const ret = String(in_action || "manual_review");
  return ret;
}

function pcIsUserModified(in_item) {
  const selectedRotation = pcNormalizeRotation(in_item.selectedRotation);
  const suggestedRotation = pcNormalizeRotation(in_item.suggestedRotation);
  const selectedAction = pcNormalizeAction(in_item.selectedAction);
  const suggestedAction = pcNormalizeAction(in_item.suggestedAction);
  const ret = selectedRotation !== suggestedRotation || selectedAction !== suggestedAction;
  return ret;
}

async function pcPersistAllActionsStateNow() {
  try {
    const out_response = await fetch("/api/actions?scope=all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pcActionsState || {}),
    });
    if (out_response.ok) {
      pcUpdateInfo("изменения сохранены в базе");
    } else {
      pcUpdateInfo("не удалось сохранить изменения в базе");
    }
  } catch (_error) {
    pcUpdateInfo("ошибка сохранения изменений");
  }
}

async function pcOrientationApplyAllSuggested() {
  if (!pcActionsState.orientation || !pcActionsState.orientation.items) {
    return;
  }
  const items = pcActionsState.orientation.items;
  let appliedCount = 0;
  let skippedModifiedCount = 0;

  for (const photoId of Object.keys(items)) {
    const item = items[photoId];
    if (!item || typeof item !== "object") {
      continue;
    }
    if (pcIsUserModified(item)) {
      skippedModifiedCount += 1;
      continue;
    }
    const suggestedRotation = pcNormalizeRotation(item.suggestedRotation);
    const suggestedAction = pcNormalizeAction(item.suggestedAction);
    pcOrientationSet(photoId, suggestedRotation, suggestedAction, true);
    appliedCount += 1;
  }

  await pcPersistAllActionsStateNow();
  pcUpdateInfo(
    `применены рекомендации: ${appliedCount}, пропущено (изменено вручную): ${skippedModifiedCount}`,
  );
}

function pcOrientationSet(in_photoId, in_rotation, in_action, in_skipSave) {
  if (!pcActionsState.orientation || !pcActionsState.orientation.items) {
    return;
  }
  const out_item = pcActionsState.orientation.items[in_photoId];
  if (!out_item) {
    return;
  }
  out_item.selectedRotation = in_rotation;
  out_item.selectedAction = in_action;
  out_item.status = "confirmed";

  const out_rotationNode = document.getElementById(`orientation-selected-${in_photoId}`);
  if (out_rotationNode) {
    out_rotationNode.textContent = in_rotation === null ? "none" : String(in_rotation);
  }
  const out_statusNode = document.getElementById(`orientation-status-${in_photoId}`);
  if (out_statusNode) {
    out_statusNode.textContent = "confirmed";
  }
  const out_actionNode = document.getElementById(`orientation-action-${in_photoId}`);
  if (out_actionNode) {
    out_actionNode.textContent = String(in_action);
  }

  let out_previewTitle = "SELECTED ORIGINAL";
  let out_previewSrc = `${pcThumbsBasePath}/${pcThumbsSubdir}/${in_photoId}_original.jpg`;
  if (in_rotation === 90) {
    out_previewTitle = "SELECTED ROTATE 90";
    out_previewSrc = `${pcThumbsBasePath}/${pcThumbsSubdir}/${in_photoId}_rotate90.jpg`;
  } else if (in_rotation === 270) {
    out_previewTitle = "SELECTED ROTATE 270";
    out_previewSrc = `${pcThumbsBasePath}/${pcThumbsSubdir}/${in_photoId}_rotate270.jpg`;
  }

  const out_previewTitleNode = document.getElementById(`orientation-preview-title-${in_photoId}`);
  if (out_previewTitleNode) {
    out_previewTitleNode.textContent = out_previewTitle;
  }
  const out_previewImageNode = document.getElementById(`orientation-preview-img-${in_photoId}`);
  if (out_previewImageNode) {
    out_previewImageNode.src = out_previewSrc;
  }
  if (!in_skipSave) {
    pcPersistActionsNow(out_item);
  }
}

function pcApplyActionToDom(in_photoId, in_actionPayload) {
  const selectedRotation = in_actionPayload.selectedRotation;
  const selectedAction = in_actionPayload.selectedAction || "manual_review";
  pcActionsState.orientation.items[in_photoId] = in_actionPayload;
  pcOrientationSet(in_photoId, selectedRotation, selectedAction, true);
}

async function pcLoadActionsFromServer() {
  try {
    const response = await fetch("/api/actions?scope=orientation", { method: "GET" });
    if (!response.ok) {
      pcUpdateInfo("не удалось прочитать actions из базы");
      return;
    }
    const payload = await response.json();
    const items = payload.items || {};
    for (const photoId of Object.keys(items)) {
      const item = items[photoId];
      if (!item || typeof item !== "object") {
        continue;
      }
      if (!pcActionsState.orientation || !pcActionsState.orientation.items) {
        continue;
      }
      if (!pcActionsState.orientation.items[photoId]) {
        continue;
      }
      pcApplyActionToDom(photoId, item);
    }
    pcUpdateInfo(`автосохранение в ${pcActionsPath}`);
  } catch (_error) {
    pcUpdateInfo("ошибка загрузки actions из базы");
  }
}

pcLoadActionsFromServer();
