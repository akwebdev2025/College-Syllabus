(() => {
  "use strict";
  const DATA_FILES = [
    "data/syllabus/ba/dsc.json",
    "data/syllabus/ba/mdc.json",
    "data/syllabus/ba/vac.json",
    "data/syllabus/ba/sec.json",
    "data/syllabus/ba/compulsory.json"
  ];
  const $ = (id) => document.getElementById(id);
  const state = { records: [], filtered: [] };
  const categoryNames = { dsc:"DSC", mdc:"MDC", vac:"VAC", sec:"SEC", compulsory:"Compulsory", aec:"AEC", hcp:"HCP", punjabi:"Punjabi" };

  function safeText(value, fallback = "Unavailable") {
    if (value === null || value === undefined || value === "") return fallback;
    if (Array.isArray(value)) return value.length ? value.join(", ") : fallback;
    return String(value);
  }
  function normalize(value) { return String(value ?? "").toLocaleLowerCase().trim(); }
  function uniqueSorted(values) {
    return [...new Set(values.filter(v => v !== null && v !== undefined && String(v).trim() !== ""))]
      .sort((a,b) => String(a).localeCompare(String(b), undefined, {numeric:true, sensitivity:"base"}));
  }
  async function loadData() {
    const responses = await Promise.all(DATA_FILES.map(async path => {
      try {
        const response = await fetch(path, { cache: "no-store" });
        if (!response.ok) return [];
        const json = await response.json();
        return Array.isArray(json) ? json : (Array.isArray(json.records) ? json.records : []);
      } catch (_) { return []; }
    }));
    state.records = responses.flat().filter(record => record && typeof record === "object" && record.subject);
    const sessions = uniqueSorted(state.records.map(r => r.academicSession));
    const updateDates = state.records.map(r => r.lastUpdated).filter(Boolean).sort();
    $("updatedStatus").textContent = state.records.length
      ? `${state.records.length} validated record${state.records.length === 1 ? "" : "s"} · ${updateDates.length ? "Data updated " + updateDates[updateDates.length - 1] : "Update date unavailable"}`
      : "Syllabus data is being prepared; check official PU sources below.";
    populateCourses();
    render(state.records);
  }
  function fillSelect(select, values, placeholder, formatter = v => v) {
    select.innerHTML = "";
    const first = document.createElement("option"); first.value = ""; first.textContent = placeholder; select.append(first);
    values.forEach(value => { const option = document.createElement("option"); option.value = value; option.textContent = formatter(value); select.append(option); });
    select.disabled = values.length === 0;
  }
  function populateCourses() {
    const courses = uniqueSorted(state.records.map(r => r.course || r.programme));
    fillSelect($("courseSelect"), courses, "All available courses", v => String(v).toUpperCase());
    updateDependentFilters();
  }
  function selectedBase() {
    const course = normalize($("courseSelect").value);
    return state.records.filter(r => !course || normalize(r.course || r.programme) === course);
  }
  function updateDependentFilters() {
    const base = selectedBase();
    fillSelect($("semesterSelect"), uniqueSorted(base.map(r => r.semester)), "All semesters");
    fillSelect($("categorySelect"), uniqueSorted(base.map(r => r.category)), "All categories", v => categoryNames[normalize(v)] || String(v).toUpperCase());
    updateSubjects();
  }
  function updateSubjects() {
    const course = normalize($("courseSelect").value), semester = normalize($("semesterSelect").value), category = normalize($("categorySelect").value);
    const rows = state.records.filter(r =>
      (!course || normalize(r.course || r.programme) === course) &&
      (!semester || normalize(r.semester) === semester) &&
      (!category || normalize(r.category) === category));
    fillSelect($("subjectSelect"), uniqueSorted(rows.map(r => r.subject)), "All subjects");
  }
  function includesQuery(record, query) {
    if (!query) return true;
    const fields = [record.subject, record.paperTitle, record.paperCode, record.category, record.semester, record.course, record.programme, record.paperType, record.academicSession];
    return fields.some(value => normalize(value).includes(query));
  }
  function search() {
    const course = normalize($("courseSelect").value), semester = normalize($("semesterSelect").value);
    const category = normalize($("categorySelect").value), subject = normalize($("subjectSelect").value);
    const query = normalize($("queryInput").value);
    state.filtered = state.records.filter(r =>
      (!course || normalize(r.course || r.programme) === course) &&
      (!semester || normalize(r.semester) === semester) &&
      (!category || normalize(r.category) === category) &&
      (!subject || normalize(r.subject) === subject) && includesQuery(r, query));
    render(state.filtered);
    $("resultsTitle").textContent = query || course || semester || category || subject ? "Search results" : "Available papers";
  }
  function addMeta(container, label, value) {
    const box = document.createElement("div"); box.className = "meta-item";
    const name = document.createElement("span"); name.textContent = label;
    const val = document.createElement("strong"); val.textContent = safeText(value);
    box.append(name, val); container.append(box);
  }
  function addDetailText(container, title, value) {
    if (value === null || value === undefined || value === "") return;
    const h = document.createElement("h4"); h.textContent = title; container.append(h);
    if (Array.isArray(value)) {
      const ul = document.createElement("ul");
      value.forEach(item => { const li = document.createElement("li"); li.textContent = typeof item === "string" ? item : JSON.stringify(item); ul.append(li); });
      container.append(ul);
    } else {
      const p = document.createElement("p"); p.textContent = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value); container.append(p);
    }
  }
  function render(records) {
    const root = $("results"), template = $("resultTemplate"); root.replaceChildren();
    $("resultCount").textContent = `${records.length} record${records.length === 1 ? "" : "s"}`;
    $("messageBox").textContent = records.length ? "" : (state.records.length
      ? "No matching papers. Try clearing one or more filters."
      : "No validated syllabus records are published yet. The search interface is ready, but records will appear only after official documents pass validation. Use the official PU source link below in the meantime.");
    records.forEach(record => {
      const card = template.content.firstElementChild.cloneNode(true);
      card.querySelector(".category-tag").textContent = safeText(record.category, "Category unavailable");
      card.querySelector(".session-tag").textContent = safeText(record.academicSession, "Session unavailable");
      card.querySelector(".paper-title").textContent = safeText(record.paperTitle, "Paper title unavailable");
      card.querySelector(".subject-name").textContent = safeText(record.subject, "Subject unavailable");
      const meta = card.querySelector(".meta-grid");
      addMeta(meta, "Course", record.course || record.programme);
      addMeta(meta, "Semester", record.semester);
      addMeta(meta, "Paper code", record.paperCode);
      addMeta(meta, "Credits", record.credits);
      const details = card.querySelector(".detail-content");
      addDetailText(details, "Paper type", record.paperType);
      addDetailText(details, "Units and topics", record.units || record.detailedTopics);
      addDetailText(details, "Examination / QP structure", record.qpStructure || record.examinationPattern);
      addDetailText(details, "Academic session", record.academicSession);
      addDetailText(details, "Last updated", record.lastUpdated);
      addDetailText(details, "Document hash", record.documentHash);
      const source = card.querySelector(".source-button");
      const url = record.sourceUrl;
      if (url && /^https:\/\/(www\.)?puchd\.ac\.in\//i.test(url) || url && /^https:\/\/(websys|www\.manuscripts)\.puchd\.ac\.in\//i.test(url)) {
        source.href = url;
      } else {
        source.removeAttribute("href"); source.textContent = "Official source unavailable"; source.style.opacity = ".6"; source.style.pointerEvents = "none";
      }
      card.querySelector(".print-button").addEventListener("click", () => {
        const detailsElement = card.querySelector("details"); detailsElement.open = true;
        window.print();
      });
      root.append(card);
    });
  }
  $("courseSelect").addEventListener("change", () => { updateDependentFilters(); search(); });
  $("semesterSelect").addEventListener("change", () => { updateSubjects(); search(); });
  $("categorySelect").addEventListener("change", () => { updateSubjects(); search(); });
  $("subjectSelect").addEventListener("change", search);
  $("searchForm").addEventListener("submit", event => { event.preventDefault(); search(); });
  $("resetButton").addEventListener("click", () => {
    $("courseSelect").value = ""; $("queryInput").value = "";
    updateDependentFilters(); $("semesterSelect").value = ""; $("categorySelect").value = ""; updateSubjects(); $("subjectSelect").value = "";
    $("resultsTitle").textContent = "Available papers"; render(state.records);
  });
  $("themeToggle").addEventListener("click", () => {
    document.body.classList.toggle("dark");
    const dark = document.body.classList.contains("dark");
    try { localStorage.setItem("csb-theme", dark ? "dark" : "light"); } catch (_) {}
    $("themeToggle").setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  });
  try { if (localStorage.getItem("csb-theme") === "dark") document.body.classList.add("dark"); } catch (_) {}
  loadData();
})();
