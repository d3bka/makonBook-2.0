import re
import os

js_path = "static/assets/js/makon-test-config.js"
api_views_path = "apps/sat/api_views.py"
views_path = "apps/sat/views.py"

# --- 1. JS UI update ---
with open(js_path, "r") as f:
    js_content = f.read()

old_modes = """    this.modes = [
      { id: "full_test", title: "Full Test", desc: "All modules (RW + Math)", baseMin: 134, isDefault: true, icon: "bi-bullseye" },
      { id: "rw_only", title: "Reading & Writing Only", desc: "Both RW modules", baseMin: 64, icon: "bi-book" },
      { id: "math_only", title: "Math Only", desc: "Both Math modules", baseMin: 70, icon: "bi-calculator" },
      { id: "single_module", title: "Single Module", desc: "Practice one module", baseMin: 32, icon: "bi-lightning-charge" }
    ];"""

new_modes = """    this.modes = [
      { id: "full_test", title: "Full Test", desc: "All modules (RW + Math)", baseMin: 134, isDefault: true, icon: "bi-bullseye" },
      { id: "rw_only", title: "Reading & Writing Only", desc: "Both RW modules", baseMin: 64, icon: "bi-book" },
      { id: "math_only", title: "Math Only", desc: "Both Math modules", baseMin: 70, icon: "bi-calculator" },
      { id: "single_english", title: "Single RW Module", desc: "Practice one English module", baseMin: 32, icon: "bi-book-half" },
      { id: "single_math", title: "Single Math Module", desc: "Practice one Math module", baseMin: 35, icon: "bi-calculator-fill" }
    ];"""

if old_modes in js_content:
    js_content = js_content.replace(old_modes, new_modes)
else:
    print("WARNING: Could not find JS old_modes block")

js_content = js_content.replace(
    "if (this.state.mode === 'single_module' && min === 32) return `~32 min`;",
    "if (this.state.mode.startsWith('single_') && min < 60) return `~${min} min`;"
)

with open(js_path, "w") as f:
    f.write(js_content)


# --- 2. API validation ---
with open(api_views_path, "r") as f:
    api_content = f.read()

api_content = api_content.replace(
    "_PTC_VALID_MODES = {'full_test', 'rw_only', 'math_only', 'single_module'}",
    "_PTC_VALID_MODES = {'full_test', 'rw_only', 'math_only', 'single_english', 'single_math'}"
)
with open(api_views_path, "w") as f:
    f.write(api_content)


# --- 3. Views Sequence Generation ---
with open(views_path, "r") as f:
    views_content = f.read()

old_seq = """def get_test_sequence(test, mode='full_test'):
    \"\"\"Return only supported SAT module slots that actually contain questions.

    Older code allowed NULL or arbitrary module values into the sequence.  The UI,
    draft models, scoring, and guest completion logic support only module_1/m1 and
    module_2/m2, so an invalid admin/import value could trap an attempt forever.
    \"\"\"
    supported = [('module_1', 'm1'), ('module_2', 'm2')]
    sequence = []
    
    english_modules = set(
        English_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'rw_only', 'single_module') else set()
    
    math_modules = set(
        Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'math_only', 'single_module') else set()
    
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
            
    if mode == 'single_module' and len(sequence) > 0:
        return [sequence[0]]
        
    return sequence"""

new_seq = """def get_test_sequence(test, mode='full_test'):
    \"\"\"Return only supported SAT module slots that actually contain questions.

    Older code allowed NULL or arbitrary module values into the sequence.  The UI,
    draft models, scoring, and guest completion logic support only module_1/m1 and
    module_2/m2, so an invalid admin/import value could trap an attempt forever.
    \"\"\"
    supported = [('module_1', 'm1'), ('module_2', 'm2')]
    sequence = []
    
    english_modules = set(
        English_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'rw_only', 'single_english') else set()
    
    math_modules = set(
        Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'math_only', 'single_math') else set()
    
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
            
    if mode in ('single_english', 'single_math') and len(sequence) > 0:
        return [sequence[0]]
        
    return sequence"""

if old_seq in views_content:
    views_content = views_content.replace(old_seq, new_seq)
else:
    print("WARNING: Could not find views sequence block")

with open(views_path, "w") as f:
    f.write(views_content)

print("Split modes applied.")
