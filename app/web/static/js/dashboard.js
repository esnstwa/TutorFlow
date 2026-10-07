(() => {
  const modalDefinitions = {
    lesson: {
      title: "Создать занятие",
      submit: "Создать занятие",
      destination: "/schedule",
      fields: [
        ["student_id", "Ученик", "student"], ["topic", "Тема занятия", "text"],
        ["date", "Дата", "date"], ["start", "Начало", "time"], ["end", "Окончание", "time"],
      ],
    },
    assignment: {
      title: "Выдать задание",
      submit: "Выдать задание",
      destination: "/assignments",
      fields: [["student_id", "Ученик", "student"], ["title", "Название задания", "text"], ["due", "Срок выполнения", "date"]],
    },
    student: {
      title: "Добавить ученика",
      submit: "Добавить ученика",
      destination: "/students",
      fields: [["name", "Имя и фамилия", "text"], ["email", "Электронная почта", "email"], ["subject", "Предмет", "text"], ["grade", "Класс", "text"]],
    },
    material: {
      title: "Загрузить материал",
      submit: "Добавить материал",
      destination: "/materials",
      fields: [["title", "Название", "text"], ["kind", "Тип материала", "material"]],
    },
  };

  let activeModalKind = null;

  const shell = () => document.querySelector("[data-teacher-shell]");
  const getStudents = () => {
    try { return JSON.parse(shell()?.querySelector("[data-student-options]")?.textContent || "[]"); }
    catch { return []; }
  };

  const setLoading = (loading) => {
    const view = document.querySelector("[data-dashboard-view]");
    if (!view) return;
    view.classList.toggle("is-loading", loading);
    view.setAttribute("aria-busy", String(loading));
  };

  async function navigate(url, { replace = false } = {}) {
    setLoading(true);
    try {
      const response = await fetch(url, { headers: { "X-TutorFlow-Navigation": "partial" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const html = await response.text();
      const page = new DOMParser().parseFromString(html, "text/html");
      const nextShell = page.querySelector("[data-teacher-shell]");
      if (!nextShell) throw new Error("Страница кабинета не найдена");
      shell().replaceWith(document.importNode(nextShell, true));
      document.title = page.title;
      if (replace) history.replaceState({}, "", url); else history.pushState({}, "", url);
      document.dispatchEvent(new CustomEvent("tutorflow:navigated"));
      window.scrollTo({ top: 0, behavior: "smooth" });
      document.querySelector("[data-dashboard-view] h1, [data-dashboard-view] h2")?.focus?.({ preventScroll: true });
    } catch (error) {
      const view = document.querySelector("[data-dashboard-view]");
      if (view) view.innerHTML = `<div class="dashboard-error"><h2>Не удалось загрузить страницу</h2><p>Проверьте соединение и попробуйте ещё раз.</p><button class="dashboard-secondary" data-retry-navigation="${url}">Повторить</button></div>`;
      console.error(error);
    } finally { setLoading(false); }
  }

  const closeProfileMenu = () => {
    const menu = document.querySelector(".dashboard-profile-dropdown");
    const trigger = document.querySelector("[data-profile-trigger]");
    if (menu) menu.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
  };

  const fieldMarkup = ([name, label, type]) => {
    if (type === "student") {
      const options = getStudents().map((student) => `<option value="${student.id}">${student.name}</option>`).join("");
      return `<label>${label}<select name="${name}" required><option value="">Выберите ученика</option>${options}</select></label>`;
    }
    if (type === "material") return `<label>${label}<select name="${name}" required><option value="PDF">PDF</option><option value="Презентация">Презентация</option><option value="Ссылка">Ссылка</option></select></label>`;
    return `<label>${label}<input name="${name}" type="${type}" required></label>`;
  };

  function openModal(kind, prefill = {}) {
    const definition = modalDefinitions[kind];
    const modal = document.querySelector("[data-modal]");
    if (!definition || !modal) return;
    activeModalKind = kind;
    modal.querySelector("[data-modal-title]").textContent = definition.title;
    modal.querySelector("[data-modal-submit]").textContent = definition.submit;
    modal.querySelector("[data-modal-fields]").innerHTML = definition.fields.map(fieldMarkup).join("");
    const form = modal.querySelector("[data-modal-form]");
    Object.entries(prefill).forEach(([name, value]) => {
      const field = form.elements.namedItem(name);
      if (field) field.value = value;
    });
    modal.querySelector("[data-modal-error]").hidden = true;
    modal.showModal();
    modal.querySelector("input, select")?.focus();
  }

  function closeModal() {
    const modal = document.querySelector("[data-modal]");
    if (modal?.open) modal.close();
    activeModalKind = null;
  }

  function showToast(message) {
    const toast = document.querySelector("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.setTimeout(() => { if (toast.isConnected) toast.hidden = true; }, 2800);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-spa]");
    if (link && link.origin === location.origin && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
      event.preventDefault();
      closeProfileMenu();
      navigate(link.href);
      return;
    }
    const retry = event.target.closest("[data-retry-navigation]");
    if (retry) { navigate(retry.dataset.retryNavigation, { replace: true }); return; }
    const profileTrigger = event.target.closest("[data-profile-trigger]");
    if (profileTrigger) {
      const menu = document.querySelector(".dashboard-profile-dropdown");
      const willOpen = menu.hidden;
      menu.hidden = !willOpen;
      profileTrigger.setAttribute("aria-expanded", String(willOpen));
      return;
    }
    if (!event.target.closest(".dashboard-profile-menu")) closeProfileMenu();
    const modalTrigger = event.target.closest("[data-open-modal]");
    if (modalTrigger) { openModal(modalTrigger.dataset.openModal); return; }
    if (event.target.closest("[data-modal-close]")) closeModal();
    const modal = event.target.closest("[data-modal]");
    if (modal && event.target === modal) closeModal();
  });

  document.addEventListener("submit", async (event) => {
    if (event.target.matches("[data-modal-form]")) {
      event.preventDefault();
      const definition = modalDefinitions[activeModalKind];
      const errorNode = event.target.querySelector("[data-modal-error]");
      const submit = event.target.querySelector("[data-modal-submit]");
      const payload = Object.fromEntries(new FormData(event.target));
      submit.disabled = true;
      submit.textContent = "Сохраняем…";
      errorNode.hidden = true;
      try {
        const response = await fetch(`/api/mock/${activeModalKind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || "Не удалось сохранить");
        closeModal();
        await navigate(definition.destination);
        showToast("Готово — данные добавлены");
      } catch (error) {
        errorNode.textContent = error.message;
        errorNode.hidden = false;
      } finally {
        submit.disabled = false;
        submit.textContent = definition.submit;
      }
      return;
    }
    if (event.target.matches("[data-settings-form]")) {
      event.preventDefault();
      const status = event.target.querySelector(".dashboard-inline-status");
      status.textContent = "Сохранено";
      window.setTimeout(() => { if (status.isConnected) status.textContent = ""; }, 2200);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeProfileMenu();
      closeModal();
    }
  });
  document.addEventListener("tutorflow:open-modal", (event) => openModal(event.detail.kind, event.detail.prefill));
  window.addEventListener("popstate", () => navigate(location.href, { replace: true }));
  window.TutorFlow = { navigate, openModal, showToast };
})();
