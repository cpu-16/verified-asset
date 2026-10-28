document.querySelectorAll('.attribute-editor').forEach(function (editor) {
  var catalogue = JSON.parse(document.getElementById('attribute-catalogue').textContent);
  var rows = Array.from(editor.querySelectorAll('.claim-row'));
  var status = editor.querySelector('.attribute-status');
  function field(row, name) { return row.querySelector('[name^="' + name + '"]'); }
  function identity(attr) { return attr.type + ':' + (attr.subject || ''); }
  function syncChips() {
    editor.querySelectorAll('.attribute-chip').forEach(function (button) {
      var selected = rows.some(function (row) { return !row.hidden && row.dataset.attribute === button.dataset.attribute; });
      button.setAttribute('aria-pressed', String(selected));
      button.setAttribute('aria-disabled', String(selected));
    });
  }
  function compact(row, attr) {
    row.dataset.compact = 'yes';
    var select = field(row, 'type');
    if (select.tagName === 'SELECT') {
      var hidden = document.createElement('input');
      hidden.type = 'hidden'; hidden.name = select.name; hidden.value = select.value;
      select.replaceWith(hidden);
    }
    field(row, 'type').parentElement.hidden = true;
    field(row, 'subject').type = 'hidden';
    var text = field(row, 'text');
    var phrase = document.createElement('button');
    phrase.type = 'button'; phrase.className = 'claim-phrase';
    // Keep the submitted sentence intact while showing a short editable phrase.
    function display() {
      phrase.textContent = row.dataset.generated || text.value === sentence(row) ? attr.label : text.value;
      phrase.setAttribute('aria-label', 'Edit claim: ' + text.value);
      text.type = 'hidden'; phrase.hidden = false;
    }
    phrase.addEventListener('click', function () {
      phrase.hidden = true; text.type = 'text'; text.focus();
    });
    text.addEventListener('blur', display);
    text.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); text.blur(); phrase.focus(); }
    });
    text.parentElement.appendChild(phrase);
    display();
  }
  function requirements(row) {
    var type = field(row, 'type').value;
    field(row, 'value').required = !row.hidden && ['piece_count', 'color', 'label_text'].includes(type);
    field(row, 'subject').required = !row.hidden && ['piece_count', 'part_no_damage'].includes(type);
    field(row, 'subject').parentElement.hidden = row.dataset.compact === 'yes' || !['piece_count', 'part_no_damage'].includes(type);
    field(row, 'value').parentElement.hidden = !['piece_count', 'color', 'label_text'].includes(type);
    field(row, 'value').type = ['piece_count', 'color', 'label_text'].includes(type) ? 'text' : 'hidden';
    field(row, 'value').setAttribute('aria-label', {piece_count: 'Number of ' + field(row, 'subject').value, color: 'Color', label_text: 'Label text'}[type] || 'Value');
    field(row, 'value').inputMode = type === 'piece_count' ? 'numeric' : 'text';
  }
  function sentence(row) {
    var type = field(row, 'type').value, value = field(row, 'value').value;
    var subject = field(row, 'subject').value;
    if (type === 'piece_count') return value + ' ' + subject + (value === '1' ? '' : 's');
    if (type === 'color') return 'Color: ' + value;
    if (type === 'label_text') return 'Label reads: ' + value;
    if (type === 'part_no_damage') return subject + ' has no visible damage';
    return 'No visible damage';
  }
  function add(attr) {
    if (attr.label && rows.some(function (r) { return !r.hidden && r.dataset.attribute === identity(attr); })) return;
    var row = rows.find(function (r) { return r.hidden; });
    if (!row) { status.textContent = 'You can add up to ' + rows.length + ' claims. Remove one to add another.'; return; }
    row.innerHTML = row.dataset.emptyMarkup;
    row.hidden = false;
    row.classList.remove('suggested');
    row.querySelectorAll('.ai-tag').forEach(function (tag) { tag.remove(); });
    field(row, 'by').value = '';
    row.dataset.compact = '';
    row.dataset.attribute = attr.label ? identity(attr) : '';
    row.dataset.generated = attr.type === 'uncheckable' ? '' : 'yes';
    ['type', 'subject', 'value'].forEach(function (key) { field(row, key).value = attr[key] || ''; });
    field(row, 'text').value = row.dataset.generated ? sentence(row) : '';
    if (attr.label) compact(row, attr);
    bind(row);
    requirements(row);
    syncChips();
    status.textContent = 'Claim added.';
    var focus = row.dataset.generated && ['piece_count', 'color', 'label_text'].includes(attr.type) ? field(row, 'value') : row.querySelector('.claim-phrase') || field(row, 'text');
    focus.focus();
  }
  editor.querySelector('.category-picker').addEventListener('change', function (event) {
    var chips = editor.querySelector('.attribute-chips'); chips.replaceChildren();
    (catalogue[event.target.value] || []).forEach(function (attr) {
      var button = document.createElement('button');
      button.type = 'button'; button.className = 'secondary attribute-chip'; button.textContent = attr.label;
      button.dataset.attribute = identity(attr);
      button.addEventListener('click', function () { add(attr); }); chips.appendChild(button);
    });
    syncChips();
  });
  editor.querySelector('.add-free').addEventListener('click', function () { add({type: 'uncheckable'}); });
  function bind(row) {
    field(row, 'text').addEventListener('input', function () { row.dataset.generated = ''; });
    ['value', 'subject', 'type'].forEach(function (key) {
      field(row, key).addEventListener('input', function () {
        requirements(row);
        if (row.dataset.generated && field(row, 'type').value !== 'uncheckable') field(row, 'text').value = sentence(row);
      });
    });
    row.querySelector('.remove-claim').addEventListener('click', function () {
      row.hidden = true; row.classList.remove('suggested');
      ['text', 'subject', 'value', 'by'].forEach(function (key) { field(row, key).value = ''; });
      requirements(row);
      syncChips();
      status.textContent = 'Claim removed.'; editor.querySelector('.add-free').focus();
    });
  }
  rows.forEach(function (row) {
    row.dataset.emptyMarkup = row.innerHTML;
    if (!row.hidden) {
      var match = Object.values(catalogue).flat().find(function (attr) {
        return attr.type === field(row, 'type').value && (attr.subject || '') === field(row, 'subject').value;
      });
      if (match) { row.dataset.attribute = identity(match); compact(row, match); }
    }
    requirements(row);
    bind(row);
  });
});
