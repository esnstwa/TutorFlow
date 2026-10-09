(() => {
  let selectedStudents = [];
  let searchTimer;
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
  const modal = () => document.querySelector("[data-homework-modal]");
  const form = () => document.querySelector("[data-homework-form]");
  const students = () => { try { return JSON.parse(document.querySelector("[data-student-options]")?.textContent || "[]"); } catch { return []; } };
  const toast = (message) => {
    if (window.TutorFlow?.showToast) window.TutorFlow.showToast(message);
    else alert(message);
  };

  function renderChips() {
    const node = document.querySelector("[data-homework-chips]");
    if (!node) return;
    node.innerHTML = selectedStudents.map((student) => `<span class="homework-chip">${escapeHtml(student.name)}<button type="button" data-homework-remove-student="${student.id}" aria-label="Удалить ${escapeHtml(student.name)}">×</button></span>`).join("");
  }

  function addStudent(student) {
    if (!student || selectedStudents.some((row) => Number(row.id) === Number(student.id))) return;
    selectedStudents.push(student); renderChips();
    const input = document.querySelector("[data-homework-student-search]");
    if (input) input.value = "";
    const results = document.querySelector("[data-homework-search-results]");
    if (results) results.hidden = true;
  }

  function openHomework(prefill = {}) {
    const dialog = modal(), homeworkForm = form();
    if (!dialog || !homeworkForm) return;
    homeworkForm.reset(); selectedStudents = [];
    homeworkForm.elements.lesson_id.value = prefill.lesson_id || "";
    const ids = (prefill.recipient_ids || []).map(Number);
    selectedStudents = students().filter((student) => ids.includes(Number(student.id)));
    renderChips();
    document.querySelector("[data-homework-file-list]").innerHTML = "";
    const error = document.querySelector("[data-homework-error]"); error.hidden = true;
    dialog.showModal(); homeworkForm.elements.title.focus();
  }

  async function findStudents(query) {
    const results = document.querySelector("[data-homework-search-results]");
    if (!results) return;
    results.hidden = false; results.innerHTML = '<div style="padding:10px 12px;font-size:12px;color:#777">Ищем…</div>';
    try {
      const response = await fetch(`/api/students/search?q=${encodeURIComponent(query)}`); const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Не удалось выполнить поиск");
      const rows = body.students.filter((student) => !selectedStudents.some((item) => Number(item.id) === Number(student.id)));
      results.innerHTML = rows.length ? rows.map((student) => `<button type="button" data-homework-add-student="${student.id}"><span>${escapeHtml(student.name)}</span><small>${escapeHtml(student.grade)} · ${escapeHtml(student.subject)}</small></button>`).join("") : '<div style="padding:10px 12px;font-size:12px;color:#777">Ничего не найдено</div>';
    } catch (error) { results.innerHTML = `<div style="padding:10px 12px;font-size:12px;color:#b44">${escapeHtml(error.message)}</div>`; }
  }

  async function uploadFiles(files, endpoint) {
    const ids = [];
    for (const file of files) {
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream", "X-Filename": encodeURIComponent(file.name) }, body: file });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Не удалось загрузить ${file.name}`);
      ids.push(body.file.id);
    }
    return ids;
  }

  async function createHomework(event) {
    event.preventDefault(); const homeworkForm = event.target;
    const button = homeworkForm.querySelector("[data-homework-submit]"), errorNode = homeworkForm.querySelector("[data-homework-error]");
    errorNode.hidden = true; button.disabled = true; button.textContent = "Сохраняем…";
    try {
      if (!selectedStudents.length) throw new Error("Выберите хотя бы одного ученика");
      const files = [...homeworkForm.querySelector("[data-homework-files]").files];
      const attachment_ids = files.length ? await uploadFiles(files, "/api/files/upload") : [];
      const payload = { title: homeworkForm.elements.title.value, description: homeworkForm.elements.description.value, recipient_ids: selectedStudents.map((item) => Number(item.id)), attachment_ids, due_at: homeworkForm.elements.due_at.value || null, lesson_id: Number(homeworkForm.elements.lesson_id.value) || null };
      const response = await fetch("/api/homework", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Не удалось выдать задание");
      modal().close(); document.dispatchEvent(new CustomEvent("tutorflow:homework-created", { detail: body.homework })); toast("Задание выдано");
      if (document.querySelector("[data-homework-list-page]")) location.reload();
    } catch (error) { errorNode.textContent = error.message.replace(/^Value error, /, ""); errorNode.hidden = false; }
    finally { button.disabled = false; button.textContent = "Выдать задание"; }
  }

  async function submitStudent(event) {
    event.preventDefault(); const submissionForm = event.target, page = submissionForm.closest("[data-student-homework]"), button = submissionForm.querySelector("[data-student-submit]"), errorNode = submissionForm.querySelector("[data-student-submit-error]");
    errorNode.hidden = true; button.disabled = true; button.textContent = "Отправляем…";
    try {
      const files = [...submissionForm.querySelector("[data-student-files]").files]; const attachment_ids = files.length ? await uploadFiles(files, "/api/student/files/upload") : [];
      const response = await fetch(`/api/student/homework/${page.dataset.recipientId}/submissions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comment: submissionForm.elements.comment.value, attachment_ids }) }); const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Не удалось отправить работу"); toast("Работа отправлена преподавателю"); location.reload();
    } catch (error) { errorNode.textContent = error.message.replace(/^Value error, /, ""); errorNode.hidden = false; button.disabled = false; button.textContent = "Отправить преподавателю"; }
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-homework-open]"); if (trigger) { openHomework(); return; }
    const close = event.target.closest("[data-homework-close]"); if (close) { modal()?.close(); return; }
    if (event.target === modal()) modal().close();
    const remove = event.target.closest("[data-homework-remove-student]"); if (remove) { selectedStudents = selectedStudents.filter((student) => Number(student.id) !== Number(remove.dataset.homeworkRemoveStudent)); renderChips(); }
    const add = event.target.closest("[data-homework-add-student]"); if (add) addStudent(students().find((student) => Number(student.id) === Number(add.dataset.homeworkAddStudent)) || { id: add.dataset.homeworkAddStudent, name: add.querySelector("span").textContent });
  });
  document.addEventListener("input", (event) => {
    if (event.target.matches("[data-homework-student-search]")) { clearTimeout(searchTimer); searchTimer = setTimeout(() => findStudents(event.target.value), 180); }
    if (event.target.matches("[data-homework-files]")) document.querySelector("[data-homework-file-list]").innerHTML = [...event.target.files].map((file) => `<span>${escapeHtml(file.name)}</span>`).join("");
    if (event.target.matches("[data-student-files]")) document.querySelector("[data-student-file-list]").innerHTML = [...event.target.files].map((file) => `<span>${escapeHtml(file.name)}</span>`).join("");
    if (event.target.matches("[data-homework-list-search]")) filterCards();
  });
  document.addEventListener("submit", (event) => { if (event.target.matches("[data-homework-form]")) createHomework(event); if (event.target.matches("[data-student-submission-form]")) submitStudent(event); });
  document.addEventListener("tutorflow:open-homework", (event) => openHomework(event.detail || {}));

  let activeFilter = "";
  function filterCards() { const q = (document.querySelector("[data-homework-list-search]")?.value || "").toLowerCase(); let visible = 0; document.querySelectorAll("[data-homework-card]").forEach((card) => { const c = JSON.parse(card.dataset.counts); const statusMatch = !activeFilter || (activeFilter === "waiting" && (c.ASSIGNED || c.REVISION_REQUIRED || c.OVERDUE)) || (activeFilter === "review" && c.SUBMITTED) || (activeFilter === "completed" && c.COMPLETED && !c.ASSIGNED && !c.SUBMITTED && !c.REVISION_REQUIRED && !c.OVERDUE); const show = card.dataset.title.includes(q) && statusMatch; card.hidden = !show; if (show) visible++; }); const empty = document.querySelector("[data-homework-empty]"); if (empty) empty.hidden = visible > 0; }
  document.addEventListener("click", (event) => { const filter = event.target.closest("[data-homework-filter]"); if (filter) { activeFilter = filter.dataset.homeworkFilter; document.querySelectorAll("[data-homework-filter]").forEach((button) => button.classList.toggle("is-active", button === filter)); filterCards(); } const review = event.target.closest("[data-review-form] button[name=action]"); if (review) { event.preventDefault(); const page = review.closest("[data-review-page]"), error = page.querySelector("[data-review-error]"); review.disabled = true; fetch(`/api/homework-recipients/${page.dataset.recipientId}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: review.value, teacher_comment: review.form.elements.teacher_comment.value }) }).then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.detail); toast(review.value === "COMPLETED" ? "Работа принята" : "Работа возвращена на доработку"); location.reload(); }).catch((err) => { error.textContent = err.message; error.hidden = false; review.disabled = false; }); } });
  document.addEventListener("change", (event) => { if (event.target.matches("[data-recipient-filter]")) { let visible = 0; document.querySelectorAll("[data-recipient-row]").forEach((row) => { row.hidden = Boolean(event.target.value && row.dataset.recipientRow !== event.target.value); if (!row.hidden) visible++; }); document.querySelector("[data-recipient-empty]").hidden = visible > 0; } });
})();
