(() => {
  const locale = "ru-RU";
  const minHour = 8;
  const maxHour = 20;
  const dayMs = 86400000;
  const statusLabels = {
    scheduled: "Запланировано",
    completed_unpaid: "Проведено и неоплачено",
    completed_paid: "Проведено и оплачено",
    cancelled: "Отменено",
  };

  const parseDate = (value) => new Date(`${value}T12:00:00`);
  const isoDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const addDays = (date, amount) => new Date(date.getTime() + amount * dayMs);
  const startOfWeek = (date) => addDays(date, -((date.getDay() + 6) % 7));
  const minutes = (value) => Number(value.split(":")[0]) * 60 + Number(value.split(":")[1]);
  const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
  const capitalize = (value) => value.charAt(0).toUpperCase() + value.slice(1);

  function initSchedule() {
    const root = document.querySelector("[data-schedule-root]");
    if (!root || root.dataset.initialized === "true") return;
    root.dataset.initialized = "true";

    const state = {
      today: parseDate(root.dataset.today),
      selected: parseDate(root.dataset.today),
      miniMonth: parseDate(root.dataset.today),
      currentTime: root.dataset.currentTime,
      view: "week",
      filters: new Set(["lessons", "reviews", "personal", "google"]),
      events: JSON.parse(root.querySelector("[data-calendar-events]").textContent || "[]"),
    };

    const canvas = root.querySelector("[data-calendar-canvas]");
    const periodLabel = root.querySelector("[data-period-label]");
    const miniTitle = root.querySelector("[data-mini-title]");
    const miniGrid = root.querySelector("[data-mini-grid]");
    const lessonDialog = root.querySelector("[data-lesson-dialog]");
    const lessonForm = root.querySelector("[data-lesson-form]");
    const materialList = root.querySelector("[data-material-list]");
    const noteCount = root.querySelector("[data-note-count]");
    let activeLessonEvent = null;
    let initialSnapshot = "";

    const visibleEvents = () => state.events.filter((event) => state.filters.has(event.type));
    const kindLabel = (type) => ({ lessons: "Занятие TutorFlow", reviews: "Проверка заданий", personal: "Личное событие", google: "Google Calendar" })[type] || "Событие";

    function rangeDays() {
      if (state.view === "day") return [state.selected];
      const start = startOfWeek(state.selected);
      return Array.from({ length: 7 }, (_, index) => addDays(start, index));
    }

    function renderPeriodLabel() {
      if (state.view === "day") {
        periodLabel.textContent = capitalize(new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" }).format(state.selected));
        return;
      }
      if (state.view === "month") {
        periodLabel.textContent = capitalize(new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(state.selected));
        return;
      }
      const days = rangeDays();
      const start = days[0];
      const end = days[6];
      const startText = new Intl.DateTimeFormat(locale, { day: "numeric", month: start.getMonth() === end.getMonth() ? undefined : "long" }).format(start);
      const endText = new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" }).format(end);
      periodLabel.textContent = `${startText} — ${endText}`;
    }

    function eventMarkup(event) {
      const duration = Math.max(minutes(event.end) - minutes(event.start), 30);
      const top = (minutes(event.start) - minHour * 60) / 60;
      const span = duration / 60;
      const isLesson = event.type === "lessons";
      const subtitle = isLesson ? event.lesson?.student?.subject || event.subtitle : event.subtitle;
      const tag = isLesson || !event.url ? "button" : "a";
      const action = tag === "a" ? `href="${escapeHtml(event.url)}" data-spa` : `type="button" data-event-id="${escapeHtml(event.id)}"`;
      const identity = event.avatar ? `<span class="schedule-event-avatar">${escapeHtml(event.avatar)}</span>` : `<span class="schedule-event-icon" aria-hidden="true">${event.type === "reviews" ? "✓" : event.type === "google" ? "G" : "•"}</span>`;
      const status = isLesson ? ` data-lesson-status="${escapeHtml(event.status || "scheduled")}" title="${escapeHtml(statusLabels[event.status] || statusLabels.scheduled)}"` : "";
      return `<${tag} class="schedule-event schedule-event--${escapeHtml(event.type)}" ${action}${status} ${event.draggable ? 'draggable="true" data-drag-event' : ""} data-calendar-event="${escapeHtml(event.id)}" style="--event-top:${top};--event-span:${span}">${identity}<span class="schedule-event-copy"><time>${escapeHtml(event.start)}–${escapeHtml(event.end)}</time><strong>${escapeHtml(event.title)}</strong><span>${escapeHtml(subtitle)}</span></span></${tag}>`;
    }

    function renderTimeline() {
      const days = rangeDays();
      const todayIso = isoDate(state.today);
      const hours = Array.from({ length: maxHour - minHour + 1 }, (_, index) => minHour + index);
      const headers = days.map((date) => {
        const current = isoDate(date);
        return `<div class="schedule-day-header${current === todayIso ? " is-today" : ""}"><strong>${new Intl.DateTimeFormat(locale, { weekday: "short" }).format(date)}</strong><span>${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(date)}</span></div>`;
      }).join("");
      const columns = days.map((date) => {
        const dateIso = isoDate(date);
        const events = visibleEvents().filter((event) => event.date === dateIso && minutes(event.start) >= minHour * 60 && minutes(event.start) <= maxHour * 60);
        const slots = Array.from({ length: maxHour - minHour }, (_, index) => `<button type="button" class="schedule-time-slot" data-empty-slot data-date="${dateIso}" data-time="${String(minHour + index).padStart(2, "0")}:00" style="--slot-index:${index}" aria-label="Создать занятие: ${dateIso}, ${minHour + index}:00"></button>`).join("");
        const nowTop = (minutes(state.currentTime) - minHour * 60) / 60;
        const nowLine = dateIso === todayIso && nowTop >= 0 && nowTop <= maxHour - minHour ? `<div class="schedule-now-line" style="--now-top:${nowTop}" aria-label="Текущее время ${state.currentTime}"></div>` : "";
        return `<div class="schedule-day-column${dateIso === todayIso ? " is-today" : ""}" data-day-column="${dateIso}">${slots}${events.map(eventMarkup).join("")}${nowLine}</div>`;
      }).join("");
      canvas.innerHTML = `<div class="schedule-calendar-grid${state.view === "day" ? " is-day" : ""}" style="--day-count:${days.length}"><div class="schedule-day-headers">${headers}</div><div class="schedule-time-scale">${hours.map((hour, index) => `<span style="--hour-index:${index}">${String(hour).padStart(2, "0")}:00</span>`).join("")}</div><div class="schedule-days-grid">${columns}</div></div>`;
    }

    function renderMonth() {
      const first = new Date(state.selected.getFullYear(), state.selected.getMonth(), 1, 12);
      const gridStart = startOfWeek(first);
      const dates = Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
      const selectedIso = isoDate(state.selected);
      const todayIso = isoDate(state.today);
      const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => `<span>${day}</span>`).join("");
      const cells = dates.map((date) => {
        const dateIso = isoDate(date);
        const events = visibleEvents().filter((event) => event.date === dateIso);
        const classes = ["schedule-month-day", date.getMonth() !== state.selected.getMonth() ? "is-outside" : "", dateIso === selectedIso ? "is-selected" : "", dateIso === todayIso ? "is-today" : ""].filter(Boolean).join(" ");
        const items = events.slice(0, 3).map((item) => {
          const isLesson = item.type === "lessons";
          const tag = isLesson || !item.url ? "button" : "a";
          const action = tag === "a" ? `href="${escapeHtml(item.url)}" data-spa` : `type="button" data-event-id="${escapeHtml(item.id)}"`;
          return `<${tag} class="schedule-month-event schedule-month-event--${escapeHtml(item.type)}" ${action}>${escapeHtml(item.start)} ${escapeHtml(item.title)}</${tag}>`;
        }).join("");
        return `<div class="${classes}"><button type="button" class="schedule-month-day-button" data-month-day="${dateIso}" aria-label="Открыть ${dateIso}"><strong>${date.getDate()}</strong></button><div class="schedule-month-events">${items}</div></div>`;
      }).join("");
      canvas.innerHTML = `<div class="schedule-month"><div class="schedule-month-weekdays">${weekdays}</div><div class="schedule-month-grid">${cells}</div></div>`;
    }

    function renderMiniCalendar() {
      miniTitle.textContent = capitalize(new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(state.miniMonth));
      const first = new Date(state.miniMonth.getFullYear(), state.miniMonth.getMonth(), 1, 12);
      const start = startOfWeek(first);
      const selectedIso = isoDate(state.selected);
      const todayIso = isoDate(state.today);
      miniGrid.innerHTML = Array.from({ length: 42 }, (_, index) => addDays(start, index)).map((date) => {
        const value = isoDate(date);
        const classes = ["schedule-mini-day", date.getMonth() !== state.miniMonth.getMonth() ? "is-outside" : "", value === selectedIso ? "is-selected" : "", value === todayIso ? "is-today" : ""].filter(Boolean).join(" ");
        return `<button type="button" class="${classes}" data-mini-date="${value}" aria-label="${new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" }).format(date)}">${date.getDate()}</button>`;
      }).join("");
    }

    function render() {
      renderPeriodLabel();
      if (state.view === "month") renderMonth(); else renderTimeline();
      renderMiniCalendar();
      root.querySelectorAll("[data-calendar-view]").forEach((button) => {
        const active = button.dataset.calendarView === state.view;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
    }

    function movePeriod(direction) {
      if (state.view === "day") state.selected = addDays(state.selected, direction);
      else if (state.view === "week") state.selected = addDays(state.selected, direction * 7);
      else state.selected = new Date(state.selected.getFullYear(), state.selected.getMonth() + direction, 1, 12);
      state.miniMonth = new Date(state.selected);
      render();
    }

    function materialRow(value = "") {
      return `<label class="schedule-material-row"><span class="schedule-material-icon" aria-hidden="true">↗</span><input type="text" name="material" maxlength="200" value="${escapeHtml(value)}" placeholder="Название или ссылка на материал"><button type="button" data-material-remove aria-label="Удалить материал">×</button></label>`;
    }

    function renderMaterials(materials = []) {
      materialList.innerHTML = materials.length ? materials.map(materialRow).join("") : '<p class="schedule-material-empty" data-material-empty>Материалы пока не добавлены</p>';
    }

    function updateNoteCount() {
      noteCount.textContent = `${lessonForm.elements.teacher_note.value.length} / 500`;
    }

    function serializeLessonForm() {
      const data = new FormData(lessonForm);
      return JSON.stringify({
        status: data.get("status") || "scheduled",
        topic: String(data.get("topic") || "").trim(),
        location: String(data.get("location") || "").trim(),
        materials: data.getAll("material").map((item) => String(item).trim()).filter(Boolean),
        teacher_note: String(data.get("teacher_note") || ""),
      });
    }

    function durationLabel(start, end) {
      const total = Math.max(minutes(end) - minutes(start), 0);
      const hours = Math.floor(total / 60);
      const rest = total % 60;
      return [hours ? `${hours} ч` : "", rest ? `${rest} мин` : ""].filter(Boolean).join(" ") || "0 мин";
    }

    function syncStatusSelection() {
      lessonForm.querySelectorAll(".schedule-status-option").forEach((option) => option.classList.toggle("is-selected", option.querySelector("input").checked));
    }

    function renderLessonHomeworks(rows = []) {
      const node = root.querySelector("[data-lesson-homeworks]");
      if (!node) return;
      if (!rows.length) { node.innerHTML = '<div class="schedule-homework-empty"><p>Домашнее задание пока не выдано</p><button type="button" data-lesson-homework-add>+ Добавить домашнее задание</button></div>'; return; }
      node.innerHTML = rows.map((item) => `<article class="schedule-homework-card"><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml((item.description || "Без описания").slice(0, 100))}</p><small>${escapeHtml(item.due)} · ${item.recipient_count} учеников</small></div><a href="/assignments/${item.id}">Открыть задание</a></article>`).join("") + '<button class="schedule-homework-more" type="button" data-lesson-homework-add>+ Добавить ещё</button>';
    }

    function openLesson(eventItem) {
      const lesson = eventItem.lesson;
      if (!lesson) return;
      activeLessonEvent = eventItem;
      lessonForm.reset();
      lessonForm.elements.status.value = lesson.status || "scheduled";
      lessonForm.elements.topic.value = lesson.topic || "";
      lessonForm.elements.location.value = lesson.location || "";
      lessonForm.elements.teacher_note.value = lesson.teacher_note || "";
      root.querySelector("[data-lesson-avatar]").textContent = lesson.student.initials;
      root.querySelector("[data-lesson-student]").textContent = lesson.student.name;
      root.querySelector("[data-lesson-meta]").textContent = `${lesson.student.grade} · ${lesson.student.subject}`;
      root.querySelector("[data-lesson-date]").textContent = capitalize(new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(parseDate(lesson.date_iso)));
      root.querySelector("[data-lesson-time]").textContent = `${lesson.start}–${lesson.end} · ${durationLabel(lesson.start, lesson.end)}`;
      renderMaterials(lesson.materials || []);
      renderLessonHomeworks(lesson.homeworks || []);
      updateNoteCount();
      syncStatusSelection();
      root.querySelector("[data-lesson-error]").hidden = true;
      initialSnapshot = serializeLessonForm();
      lessonDialog.showModal();
      lessonDialog.querySelector("[data-lesson-close]").focus();
    }

    function hasUnsavedChanges() {
      return lessonDialog.open && initialSnapshot && serializeLessonForm() !== initialSnapshot;
    }

    function closeLesson({ force = false } = {}) {
      if (!lessonDialog.open) return;
      if (!force && hasUnsavedChanges() && !window.confirm("Закрыть без сохранения? Внесённые изменения будут потеряны.")) return;
      initialSnapshot = "";
      activeLessonEvent = null;
      lessonDialog.close();
    }

    function openGenericEvent(eventItem) {
      const dialog = root.querySelector("[data-event-dialog]");
      dialog.querySelector("[data-event-kind]").textContent = kindLabel(eventItem.type);
      dialog.querySelector("[data-event-title]").textContent = eventItem.title;
      dialog.querySelector("[data-event-subtitle]").textContent = eventItem.subtitle || "";
      dialog.querySelector("[data-event-time]").textContent = `${new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" }).format(parseDate(eventItem.date))}, ${eventItem.start}–${eventItem.end}`;
      dialog.showModal();
    }

    function openEvent(eventItem) {
      if (eventItem.type === "lessons") openLesson(eventItem);
      else openGenericEvent(eventItem);
    }

    root.addEventListener("click", (event) => {
      if (event.target.closest("[data-calendar-prev]")) movePeriod(-1);
      else if (event.target.closest("[data-calendar-next]")) movePeriod(1);
      else if (event.target.closest("[data-calendar-today]")) { state.selected = new Date(state.today); state.miniMonth = new Date(state.today); render(); }
      else if (event.target.closest("[data-calendar-view]")) { state.view = event.target.closest("[data-calendar-view]").dataset.calendarView; render(); }
      else if (event.target.closest("[data-mini-prev]")) { state.miniMonth = new Date(state.miniMonth.getFullYear(), state.miniMonth.getMonth() - 1, 1, 12); renderMiniCalendar(); }
      else if (event.target.closest("[data-mini-next]")) { state.miniMonth = new Date(state.miniMonth.getFullYear(), state.miniMonth.getMonth() + 1, 1, 12); renderMiniCalendar(); }
      else if (event.target.closest("[data-mini-date]")) { state.selected = parseDate(event.target.closest("[data-mini-date]").dataset.miniDate); state.miniMonth = new Date(state.selected); render(); }
      else if (event.target.closest("[data-month-day]")) { state.selected = parseDate(event.target.closest("[data-month-day]").dataset.monthDay); state.view = "day"; state.miniMonth = new Date(state.selected); render(); }
      else if (event.target.closest("[data-empty-slot]")) {
        const slot = event.target.closest("[data-empty-slot]");
        const end = `${String(Number(slot.dataset.time.slice(0, 2)) + 1).padStart(2, "0")}:00`;
        document.dispatchEvent(new CustomEvent("tutorflow:open-modal", { detail: { kind: "lesson", prefill: { date: slot.dataset.date, start: slot.dataset.time, end } } }));
      } else if (event.target.closest("[data-event-id]")) {
        const item = state.events.find((candidate) => candidate.id === event.target.closest("[data-event-id]").dataset.eventId);
        if (item) openEvent(item);
      } else if (event.target.closest("[data-lesson-close]")) closeLesson();
      else if (event.target === lessonDialog) closeLesson();
      else if (event.target.closest("[data-material-add]")) {
        materialList.querySelector("[data-material-empty]")?.remove();
        materialList.insertAdjacentHTML("beforeend", materialRow());
        materialList.querySelector(".schedule-material-row:last-child input")?.focus();
      } else if (event.target.closest("[data-material-remove]")) {
        event.target.closest(".schedule-material-row").remove();
        if (!materialList.children.length) renderMaterials();
      } else if (event.target.closest("[data-lesson-delete]")) deleteActiveLesson();
      else if (event.target.closest("[data-lesson-homework-add]")) {
        const lesson = activeLessonEvent?.lesson;
        if (lesson) document.dispatchEvent(new CustomEvent("tutorflow:open-homework", { detail: { lesson_id: lesson.id, recipient_ids: [lesson.student.id] } }));
      }
      else if (event.target.closest("[data-event-close]")) root.querySelector("[data-event-dialog]").close();
      else if (event.target === root.querySelector("[data-event-dialog]")) root.querySelector("[data-event-dialog]").close();
      else if (event.target.closest("[data-google-connect]")) root.querySelector("[data-google-note]").hidden = false;
    });

    root.addEventListener("input", (event) => {
      if (event.target === lessonForm.elements.teacher_note) updateNoteCount();
    });

    root.addEventListener("change", (event) => {
      const filter = event.target.closest("[data-calendar-filter]");
      if (filter) {
        if (filter.checked) state.filters.add(filter.value); else state.filters.delete(filter.value);
        render();
        return;
      }
      if (event.target.matches('input[name="status"]')) syncStatusSelection();
    });

    lessonDialog.addEventListener("cancel", (event) => { event.preventDefault(); closeLesson(); });
    document.addEventListener("tutorflow:homework-created", (event) => {
      if (!activeLessonEvent?.lesson || Number(event.detail.lesson?.id) !== Number(activeLessonEvent.lesson.id)) return;
      activeLessonEvent.lesson.homeworks = [...(activeLessonEvent.lesson.homeworks || []), event.detail];
      renderLessonHomeworks(activeLessonEvent.lesson.homeworks);
    });

    lessonForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!activeLessonEvent) return;
      const saveButton = root.querySelector("[data-lesson-save]");
      const errorNode = root.querySelector("[data-lesson-error]");
      const payload = JSON.parse(serializeLessonForm());
      saveButton.disabled = true;
      saveButton.textContent = "Сохраняем…";
      errorNode.hidden = true;
      try {
        const response = await fetch(`/api/mock/lessons/${activeLessonEvent.entity_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || "Не удалось сохранить изменения");
        activeLessonEvent.lesson = result.lesson;
        activeLessonEvent.status = result.lesson.status;
        activeLessonEvent.subtitle = `${result.lesson.student.subject} · ${result.lesson.topic}`;
        initialSnapshot = serializeLessonForm();
        render();
        closeLesson({ force: true });
        window.TutorFlow?.showToast("Изменения сохранены");
      } catch (error) {
        errorNode.textContent = error.message;
        errorNode.hidden = false;
      } finally {
        saveButton.disabled = false;
        saveButton.textContent = "Сохранить изменения";
      }
    });

    async function deleteActiveLesson() {
      if (!activeLessonEvent || !window.confirm("Удалить занятие? Это действие нельзя отменить.")) return;
      const deleteButton = root.querySelector("[data-lesson-delete]");
      deleteButton.disabled = true;
      try {
        const response = await fetch(`/api/mock/lessons/${activeLessonEvent.entity_id}`, { method: "DELETE" });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || "Не удалось удалить занятие");
        state.events = state.events.filter((item) => item.id !== activeLessonEvent.id);
        render();
        closeLesson({ force: true });
        window.TutorFlow?.showToast("Занятие удалено");
      } catch (error) {
        const errorNode = root.querySelector("[data-lesson-error]");
        errorNode.textContent = error.message;
        errorNode.hidden = false;
      } finally { deleteButton.disabled = false; }
    }

    root.addEventListener("dragstart", (event) => {
      const card = event.target.closest("[data-drag-event]");
      if (!card) return;
      card.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.calendarEvent);
    });
    root.addEventListener("dragend", (event) => event.target.closest("[data-drag-event]")?.classList.remove("is-dragging"));
    root.addEventListener("dragover", (event) => {
      const slot = event.target.closest("[data-empty-slot]");
      if (!slot) return;
      event.preventDefault();
      slot.classList.add("schedule-drop-target");
    });
    root.addEventListener("dragleave", (event) => event.target.closest("[data-empty-slot]")?.classList.remove("schedule-drop-target"));
    root.addEventListener("drop", async (event) => {
      const slot = event.target.closest("[data-empty-slot]");
      if (!slot) return;
      event.preventDefault();
      slot.classList.remove("schedule-drop-target");
      const item = state.events.find((candidate) => candidate.id === event.dataTransfer.getData("text/plain"));
      if (!item?.entity_id) return;
      try {
        const response = await fetch(`/api/mock/lessons/${item.entity_id}/reschedule`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ date: slot.dataset.date, start: slot.dataset.time }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Не удалось перенести занятие");
        item.date = result.lesson.date_iso;
        item.start = result.lesson.start;
        item.end = result.lesson.end;
        Object.assign(item.lesson, result.lesson);
        render();
        window.TutorFlow?.showToast("Занятие перенесено");
      } catch (error) { window.TutorFlow?.showToast(error.message); }
    });

    render();
  }

  document.addEventListener("DOMContentLoaded", initSchedule);
  document.addEventListener("tutorflow:navigated", initSchedule);
  initSchedule();
})();
