const state = {
  task: null,
};

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

function renderBadges(badges) {
  const badgeList = document.getElementById("badgeList");
  const template = document.getElementById("badgeTemplate");
  badgeList.innerHTML = "";
  if (!badges.length) {
    badgeList.textContent = "First badge unlocks after Gwen completes a drill.";
    return;
  }
  badges.forEach((badge) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.textContent = badge;
    badgeList.appendChild(node);
  });
}

function renderTask(task) {
  state.task = task;
  document.getElementById("taskTitle").textContent = task.title;
  document.getElementById("taskTagline").textContent = task.tagline;
  document.getElementById("taskScenario").textContent = task.scenario;
  document.getElementById("taskInstructions").textContent = task.instructions;
  document.getElementById("taskReason").textContent = task.recommendation_reason || task.reason || "";
  document.getElementById("taskLevelChip").textContent = `Level ${task.level}`;
  document.getElementById("taskPointsChip").textContent = `${task.points}+ pts`;
  document.getElementById("taskFocusChip").textContent = task.focus;
}

function renderProfile(data) {
  const profile = data.profile;
  const meter = Math.round(profile.completion_ratio * 100);
  document.getElementById("levelValue").textContent = profile.skill_level;
  document.getElementById("pointsValue").textContent = profile.total_points;
  document.getElementById("streakValue").textContent = `${profile.streak_days} day`;
  document.getElementById("badgeValue").textContent = profile.badges.length;
  document.getElementById("meterText").textContent = `${meter}%`;
  document.getElementById("meterFill").style.width = `${meter}%`;
  document.getElementById("summaryLine").textContent =
    profile.feedback_summary || "Gwen is just getting started.";
  renderBadges(profile.badges);
  renderTask(data.next_task);
}

async function refreshState() {
  const data = await getJson("/api/profile-state");
  renderProfile(data);
}

async function refreshTaskOnly() {
  const data = await getJson("/api/next-task");
  renderTask({
    ...data.task,
    recommendation_reason: data.reason,
  });
}

async function submitTask(event) {
  event.preventDefault();
  if (!state.task) return;

  const responseText = document.getElementById("responseText");
  const feedbackText = document.getElementById("feedbackText");
  const submitButton = event.target.querySelector("button[type='submit']");
  submitButton.disabled = true;
  submitButton.textContent = "Scoring…";

  try {
    const result = await getJson("/api/submit-task", {
      method: "POST",
      body: JSON.stringify({
        learner_name: "Gwen",
        task_id: state.task.id,
        response_text: responseText.value,
        gwen_feedback: feedbackText.value,
      }),
    });
    responseText.value = "";
    feedbackText.value = "";
    renderProfile({
      profile: result.profile,
      next_task: result.next_task,
    });
    document.getElementById("summaryLine").textContent =
      `${result.result.coach_feedback} Badge unlocked: ${result.result.badge_unlocked}.`;
  } catch (error) {
    document.getElementById("summaryLine").textContent = error.message;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Complete drill";
  }
}

document.getElementById("taskForm").addEventListener("submit", submitTask);
document.getElementById("refreshTaskButton").addEventListener("click", refreshTaskOnly);

refreshState().catch((error) => {
  document.getElementById("summaryLine").textContent = error.message;
});
