const pcReportConfigNode = document.getElementById("pc-report-config");
const pcActionsPath = pcReportConfigNode ? String(pcReportConfigNode.dataset.actionsPath || "../actions.json") : "../actions.json";
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
  in_scope,
) {
  const scope = in_scope || "duplicates";
  pcPendingPayload = {
    payload: in_payload,
    scope: scope,
  };
  if (pcIsSaving) {
    pcHasPendingSave = true;
    return;
  }
  pcIsSaving = true;
  try {
    const pendingEntry = pcPendingPayload;
    pcPendingPayload = null;
    const payloadToSend = pendingEntry ? pendingEntry.payload : {};
    const scopeToSend = pendingEntry ? pendingEntry.scope : "duplicates";
    const out_response = await fetch(`/api/actions?scope=${scopeToSend}`, {
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

function pcDupSetSelection(in_groupKey, in_photoId, in_skipSave) {
  if (!pcActionsState.duplicates || !pcActionsState.duplicates.groups) {
    return;
  }
  const out_group = pcActionsState.duplicates.groups[in_groupKey];
  if (!out_group) {
    return;
  }
  out_group.selectedKeepPhotoId = in_photoId;
  out_group.status = "confirmed";
  const out_selectedNode = document.getElementById(`dup-selected-${in_groupKey}`);
  if (out_selectedNode) {
    out_selectedNode.textContent = in_photoId;
  }
  const out_statusNode = document.getElementById(`dup-status-${in_groupKey}`);
  if (out_statusNode) {
    out_statusNode.textContent = "confirmed";
  }
  if (!in_skipSave) {
    pcPersistActionsNow(out_group);
  }
}

function pcDupAcceptRecommended(in_groupKey, in_recommendedPhotoId) {
  pcDupSetSelection(in_groupKey, in_recommendedPhotoId, false);
  const out_radio = document.querySelector(`input[name="dup-${in_groupKey}"][value="${in_recommendedPhotoId}"]`);
  if (out_radio) {
    out_radio.checked = true;
  }
}

function pcDupApplySelected(in_groupKey) {
  const out_selectedRadio = document.querySelector(`input[name="dup-${in_groupKey}"]:checked`);
  if (!out_selectedRadio) {
    return;
  }
  pcDupSetSelection(in_groupKey, out_selectedRadio.value, false);
}

function pcDupApplyAllRecommended() {
  if (!pcActionsState.duplicates || !pcActionsState.duplicates.groups) {
    return;
  }
  const groups = pcActionsState.duplicates.groups;
  for (const groupKey of Object.keys(groups)) {
    const group = groups[groupKey];
    if (!group) {
      continue;
    }
    const recommendedPhotoId = String(group.recommendedKeepPhotoId || "");
    if (!recommendedPhotoId) {
      continue;
    }
    pcDupSetSelection(groupKey, recommendedPhotoId, true);
    const out_radio = document.querySelector(`input[name="dup-${groupKey}"][value="${recommendedPhotoId}"]`);
    if (out_radio) {
      out_radio.checked = true;
    }
  }
  const payload = {
    duplicates: {
      groups: groups,
    },
  };
  pcPersistActionsNow(payload, "all");
}

async function pcLoadActionsFromServer() {
  try {
    const response = await fetch("/api/actions?scope=duplicates", { method: "GET" });
    if (!response.ok) {
      pcUpdateInfo("не удалось прочитать actions из базы");
      return;
    }
    const payload = await response.json();
    const groups = payload.groups || {};
    if (!pcActionsState.duplicates || !pcActionsState.duplicates.groups) {
      return;
    }
    for (const groupKey of Object.keys(groups)) {
      const group = groups[groupKey];
      if (!group || typeof group !== "object") {
        continue;
      }
      const selectedKeepPhotoId = String(group.selectedKeepPhotoId || "");
      if (!selectedKeepPhotoId) {
        continue;
      }
      if (!pcActionsState.duplicates.groups[groupKey]) {
        continue;
      }
      pcActionsState.duplicates.groups[groupKey] = group;
      pcDupSetSelection(groupKey, selectedKeepPhotoId, true);
      const out_radio = document.querySelector(`input[name="dup-${groupKey}"][value="${selectedKeepPhotoId}"]`);
      if (out_radio) {
        out_radio.checked = true;
      }
    }
    pcUpdateInfo(`автосохранение в ${pcActionsPath}`);
  } catch (_error) {
    pcUpdateInfo("ошибка загрузки actions из базы");
  }
}

pcLoadActionsFromServer();
