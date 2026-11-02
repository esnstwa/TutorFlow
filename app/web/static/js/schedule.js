(() => {
  const locale = "ru-RU";
  const minHour = 0;
  const maxHour = 24;
  const dayMs = 86400000;
  const statusLabels = {
    scheduled: "Запланировано",
    completed_unpaid: "Проведено и неоплачено",
    completed_paid: "Проведено и оплачено",
    cancelled: "Отменено",
  };

  const parseDate = (value) => new Date(`${value}T12:00:00`);
  const isoDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const addDays = (date, amount) => { const result = new Date(date); result.setDate(result.getDate() + amount); return result; };
  const startOfWeek = (date) => addDays(date, -((date.getDay() + 6) % 7));
  const minutes = (value) => Number(value.split(":")[0]) * 60 + Number(value.split(":")[1]);
  // Moscow wall-time arithmetic must not depend on the browser timezone.
  const wallStamp = (date, time) => Date.parse(`${date}T${time}:00Z`);
  const lessonDuration = (lesson) => (wallStamp(lesson.end_date_iso || lesson.date_iso, lesson.end) - wallStamp(lesson.date_iso, lesson.start)) / 60000;
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
      filters: new Set(["lessons", "reviews"]),
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
    let pending = false;

    function setPending(value) {
      pending = value;
      lessonDialog.setAttribute("aria-busy", String(value));
      lessonForm.querySelectorAll("input, select, textarea, button").forEach((field) => { field.disabled = value; });
      root.querySelector("[data-lesson-save]").disabled = value;
      root.querySelector("[data-lesson-delete]").disabled = value;
      root.querySelectorAll("[data-lesson-close]").forEach((button) => { button.disabled = value; });
    }

    const visibleEvents = () => state.events.filter((event) => state.filters.has(event.type));
    function eventsOn(dateIso) {
      const dayStart = wallStamp(dateIso, "00:00");
      const dayEnd = dayStart + dayMs;
      return visibleEvents().flatMap((event) => {
        const start = Math.max(dayStart, wallStamp(event.date, event.start));
        const end = Math.min(dayEnd, wallStamp(event.end_date || event.lesson?.end_date_iso || event.date, event.end));
        if (!(end > start)) return [];
        return [{ ...event, start: new Date(start).toISOString().slice(11, 16), end: end === dayEnd ? "24:00" : new Date(end).toISOString().slice(11, 16) }];
      });
    }
    const kindLabel = (type) => ({ lessons: "Занятие TutorFlow", reviews: "Проверка заданий" })[type] || "Событие";

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
      const duration = Math.max(minutes(event.end) - minutes(event.start), 1);
      const top = (minutes(event.start) - minHour * 60) / 60;
      const span = duration / 60;
      const isLesson = event.type === "lessons";
      const subtitle = event.subtitle;
      const tag = isLesson || !event.url ? "button" : "a";
      const action = tag === "a" ? `href="${escapeHtml(event.url)}" data-spa` : `type="button" data-event-id="${escapeHtml(event.id)}"`;
      const identity = event.avatar ? `<span class="schedule-event-avatar">${escapeHtml(event.avatar)}</span>` : `<span class="schedule-event-icon" aria-hidden="true">${event.type === "reviews" ? "✓" : "•"}</span>`;
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
        const events = eventsOn(dateIso);
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
        const events = eventsOn(dateIso);
        const classes = ["schedule-month-day", date.getMonth() !== state.selected.getMonth() ? "is-outside" : "", dateIso === selectedIso ? "is-selected" : "", dateIso === todayIso ? "is-today" : ""].filter(Boolean).join(" ");
        const items = events.map((item) => {
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
      const dates = state.view === "month"
        ? Array.from({ length: 42 }, (_, index) => isoDate(addDays(startOfWeek(new Date(state.selected.getFullYear(), state.selected.getMonth(), 1, 12)), index)))
        : rangeDays().map(isoDate);
      const hasEvents = dates.some((date) => eventsOn(date).length);
      const calendarStatus = root.querySelector("[data-calendar-status]");
      if (calendarStatus) calendarStatus.textContent = hasEvents ? "Время занятий — Москва (UTC+3)." : "Нет событий в выбранном периоде с текущими фильтрами. Можно создать занятие.";
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
        student_id: Number(data.get("student_id")),
        date: data.get("date"), start: data.get("start"),
        end: data.get("end"), end_date: data.get("end_date"),
        subject: String(data.get("subject") || "").trim(),
        meeting_url: String(data.get("meeting_url") || "").trim(),
        status: data.get("status") || "scheduled",
        topic: String(data.get("topic") || "").trim(),
        location: String(data.get("location") || "").trim(),
        materials: data.getAll("material").map((item) => String(item).trim()).filter(Boolean),
        teacher_note: String(data.get("teacher_note") || ""),
      });
    }

    function durationLabel(total) {
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
      if (pending) return;
      const lesson = eventItem.lesson;
      if (!lesson) return;
      activeLessonEvent = eventItem;
      lessonForm.reset();
      let students = [];
      try { students = JSON.parse(document.querySelector("[data-student-options]")?.textContent || "[]"); } catch { /* Keep the current student selectable. */ }
      if (!students.some((student) => Number(student.id) === Number(lesson.student.id))) students.push(lesson.student);
      lessonForm.elements.student_id.innerHTML = students.map((student) => `<option value="${escapeHtml(student.id)}">${escapeHtml(student.name)}</option>`).join("");
      lessonForm.elements.student_id.value = lesson.student_id || lesson.student.id;
      lessonForm.elements.date.value = lesson.date_iso;
      lessonForm.elements.end_date.value = lesson.end_date_iso || lesson.date_iso;
      lessonForm.elements.start.value = lesson.start;
      lessonForm.elements.end.value = lesson.end;
      lessonForm.elements.duration.value = lessonDuration(lesson);
      lessonForm.elements.subject.value = lesson.subject || "";
      lessonForm.elements.meeting_url.value = lesson.meeting_url || "";
      lessonForm.elements.status.value = lesson.status || "scheduled";
      lessonForm.elements.topic.value = lesson.topic || "";
      lessonForm.elements.location.value = lesson.location || "";
      lessonForm.elements.teacher_note.value = lesson.teacher_note || "";
      root.querySelector("[data-lesson-avatar]").textContent = lesson.student.initials;
      root.querySelector("[data-lesson-student]").textContent = lesson.student.name;
      root.querySelector("[data-lesson-meta]").textContent = `${lesson.student.grade} · ${lesson.student.subject}`;
      root.querySelector("[data-lesson-date]").textContent = capitalize(new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(parseDate(lesson.date_iso)));
      root.querySelector("[data-lesson-time]").textContent = `${lesson.start}–${lesson.end}${lesson.end_date_iso && lesson.end_date_iso !== lesson.date_iso ? ` (${lesson.end_date_iso})` : ""} · ${durationLabel(lessonDuration(lesson))}`;
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

    function syncLessonEvent(item, lesson) {
      Object.assign(item, {
        lesson, entity_id: lesson.id, title: lesson.student.name, avatar: lesson.student.initials,
        date: lesson.date_iso, start: lesson.start, end: lesson.end, status: lesson.status,
        subtitle: `${lesson.subject} · ${lesson.topic}`, url: `/lessons/${lesson.id}`,
      });
      state.selected = parseDate(lesson.date_iso);
      state.miniMonth = new Date(state.selected);
    }

    function closeLesson({ force = false } = {}) {
      if (pending || !lessonDialog.open) return;
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
      if (pending) return;
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
        const end = new Date(wallStamp(slot.dataset.date, slot.dataset.time) + 3600000).toISOString();
        document.dispatchEvent(new CustomEvent("tutorflow:open-modal", { detail: { kind: "lesson", prefill: { date: slot.dataset.date, start: slot.dataset.time, end_date: end.slice(0, 10), end: end.slice(11, 16) } } }));
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
      } else if (event.target.closest("[data-lesson-delete]")) return deleteActiveLesson();
      else if (event.target.closest("[data-lesson-homework-add]")) {
        const lesson = activeLessonEvent?.lesson;
        if (lesson) document.dispatchEvent(new CustomEvent("tutorflow:open-homework", { detail: { lesson_id: lesson.id, recipient_ids: [lesson.student.id] } }));
      }
      else if (event.target.closest("[data-event-close]")) root.querySelector("[data-event-dialog]").close();
      else if (event.target === root.querySelector("[data-event-dialog]")) root.querySelector("[data-event-dialog]").close();

    });

    root.addEventListener("input", (event) => {
      if (event.target === lessonForm.elements.teacher_note) updateNoteCount();
      if (pending) return;
      const fields = lessonForm.elements;
      const name = event.target.name;
      if (["date", "start", "duration"].includes(name)) {
        const duration = Number(fields.duration.value);
        const stamp = wallStamp(fields.date.value, fields.start.value) + duration * 60000;
        if (duration > 0 && Number.isFinite(stamp)) {
          const end = new Date(stamp).toISOString();
          fields.end_date.value = end.slice(0, 10);
          fields.end.value = end.slice(11, 16);
        }
      } else if (["end", "end_date"].includes(name)) {
        const duration = (wallStamp(fields.end_date.value, fields.end.value) - wallStamp(fields.date.value, fields.start.value)) / 60000;
        fields.duration.value = Number.isFinite(duration) && duration > 0 ? duration : "";
      }
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
    document.addEventListener("tutorflow:before-navigate", (event) => {
      if (!root.isConnected) return;
      if (pending || (hasUnsavedChanges() && !window.confirm("Уйти без сохранения изменений занятия?"))) event.preventDefault();
    });
    document.addEventListener("tutorflow:homework-created", (event) => {
      if (!activeLessonEvent?.lesson || Number(event.detail.lesson?.id) !== Number(activeLessonEvent.lesson.id)) return;
      activeLessonEvent.lesson.homeworks = [...(activeLessonEvent.lesson.homeworks || []), event.detail];
      renderLessonHomeworks(activeLessonEvent.lesson.homeworks);
    });

    lessonForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!activeLessonEvent || pending) return;
      const saveButton = root.querySelector("[data-lesson-save]");
      const errorNode = root.querySelector("[data-lesson-error]");
      const payload = JSON.parse(serializeLessonForm());
      if (payload.status === "cancelled" && activeLessonEvent.lesson.status !== "cancelled" && !window.confirm("Отменить занятие?")) return;
      setPending(true);
      saveButton.textContent = "Сохраняем…";
      errorNode.hidden = true;
      try {
        const response = await fetch(`/api/lessons/${activeLessonEvent.entity_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || result.detail || "Не удалось сохранить изменения");
        syncLessonEvent(activeLessonEvent, result.lesson);
        render();
        setPending(false);
        closeLesson({ force: true });
        window.TutorFlow?.showToast("Изменения сохранены");
      } catch (error) {
        errorNode.textContent = error.message;
        errorNode.hidden = false;
      } finally {
        setPending(false);
        saveButton.textContent = "Сохранить изменения";
      }
    });

    async function deleteActiveLesson() {
      if (!activeLessonEvent || pending || !window.confirm("Удалить занятие? Это действие нельзя отменить.")) return;
      setPending(true);
      try {
        const response = await fetch(`/api/lessons/${activeLessonEvent.entity_id}`, { method: "DELETE" });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || result.detail || "Не удалось удалить занятие");
        state.events = state.events.filter((item) => item.id !== activeLessonEvent.id);
        render();
        setPending(false);
        closeLesson({ force: true });
        window.TutorFlow?.showToast("Занятие удалено");
      } catch (error) {
        const errorNode = root.querySelector("[data-lesson-error]");
        errorNode.textContent = error.message;
        errorNode.hidden = false;
      } finally { setPending(false); }
    }

    root.addEventListener("dragstart", (event) => {
      const card = event.target.closest("[data-drag-event]");
      if (!card || pending) { event.preventDefault(); return; }
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
      if (!item?.entity_id || pending) return;
      setPending(true);
      try {
        const response = await fetch(`/api/lessons/${item.entity_id}/reschedule`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ date: slot.dataset.date, start: slot.dataset.time }) });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || result.detail || "Не удалось перенести занятие");
        syncLessonEvent(item, result.lesson);
        render();
        window.TutorFlow?.showToast("Занятие перенесено");
      } catch (error) { window.TutorFlow?.showToast(error.message); }
      finally { setPending(false); }
    });

    const lessonId = new URLSearchParams(window.location.search).get("lesson");
    const selectedLesson = state.events.find((event) => event.type === "lessons" && String(event.entity_id) === lessonId);
    if (selectedLesson) {
      state.selected = parseDate(selectedLesson.date);
      state.miniMonth = new Date(state.selected);
    }
    render();
    if (selectedLesson) openLesson(selectedLesson);
  }

  document.addEventListener("DOMContentLoaded", initSchedule);
  document.addEventListener("tutorflow:navigated", initSchedule);
  initSchedule();
})();
