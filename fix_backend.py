import re
import os

views_path = "apps/sat/views.py"
api_views_path = "apps/sat/api_views.py"

# --- 1. Fix api_views.py ---
with open(api_views_path, "w") as f:
    f.write("""import json
from django.http import JsonResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.sat.models import Test
from apps.sat.views import _get_or_create_regular_test_stage

_PTC_VALID_MODES = {'full_test', 'rw_only', 'math_only', 'single_module'}
_PTC_VALID_MULTIPLIERS = {0.5, 0.75, 1.0, 1.5, 2.0}

@login_required(login_url='/login/')
@require_POST
def initialize_test(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'error': 'Invalid JSON'}, status=400)

    test_name = str(payload.get('test_name', '')).strip()
    
    if 'mode' not in payload:
        return JsonResponse({'status': 'error', 'error': 'mode is required'}, status=400)
    mode = str(payload.get('mode')).strip()
    
    if 'multiplier' not in payload:
        return JsonResponse({'status': 'error', 'error': 'multiplier is required'}, status=400)
        
    try:
        multiplier = float(payload.get('multiplier'))
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'error': 'Invalid multiplier type'}, status=400)

    if not test_name:
        return JsonResponse({'status': 'error', 'error': 'test_name is required'}, status=400)
    if mode not in _PTC_VALID_MODES:
        return JsonResponse({'status': 'error', 'error': f'Invalid mode: {mode}'}, status=400)
    if multiplier not in _PTC_VALID_MULTIPLIERS:
        return JsonResponse({'status': 'error', 'error': f'Invalid multiplier: {multiplier}'}, status=400)

    test = Test.objects.filter(name=test_name).first()
    if not test:
        return JsonResponse({'status': 'error', 'error': 'Test not found'}, status=404)

    classroom_id = payload.get('classroom_id')
    classroom = None
    if classroom_id:
        try:
            classroom_id = int(classroom_id)
            from apps.sat.models import Classroom
            classroom = Classroom.objects.filter(id=classroom_id).first()
        except (ValueError, TypeError):
            pass

    # Initialize via "TestEngine" equivalent
    stage, created = _get_or_create_regular_test_stage(
        request.user, 
        test, 
        stage=1, 
        classroom=classroom, 
        mode=mode, 
        time_multiplier=multiplier
    )

    if classroom_id:
        start_url = reverse('classroom_practise', kwargs={'classroom_id': classroom_id, 'pk': test_name})
    else:
        start_url = reverse('test', kwargs={'pk': test_name})

    return JsonResponse({
        'status': 'success',
        'redirect_url': start_url
    })
""")

# --- 2. Fix views.py ---
with open(views_path, "r") as f:
    views_content = f.read()

# Fix _get_or_create_regular_test_stage
old_get_stage = """def _get_or_create_regular_test_stage(user, test_obj, *, stage=1, classroom=None, mode='full_test', time_multiplier=1.0):
    existing_stage = _latest_regular_test_stage(user, test_obj, classroom=classroom)
    if existing_stage:
        # Update existing config if it was restarted or resumed with different settings
        if existing_stage.mode != mode or existing_stage.time_multiplier != time_multiplier:
            existing_stage.mode = mode
            existing_stage.time_multiplier = time_multiplier
            existing_stage.save(update_fields=['mode', 'time_multiplier'])
        return existing_stage, False

    return TestStage.objects.create(
        user=user,
        test=test_obj,
        classroom=classroom,
        test_type='regular',
        stage=stage,
        mode=mode,
        time_multiplier=time_multiplier,
    ), True"""

new_get_stage = """def _get_or_create_regular_test_stage(user, test_obj, *, stage=1, classroom=None, mode=None, time_multiplier=None):
    existing_stage = _latest_regular_test_stage(user, test_obj, classroom=classroom)
    
    if existing_stage:
        # Update existing config only if explicitly provided
        update_fields = []
        if mode is not None and existing_stage.mode != mode:
            existing_stage.mode = mode
            update_fields.append('mode')
        if time_multiplier is not None and existing_stage.time_multiplier != time_multiplier:
            existing_stage.time_multiplier = time_multiplier
            update_fields.append('time_multiplier')
            
        if update_fields:
            existing_stage.save(update_fields=update_fields)
            
        return existing_stage, False

    return TestStage.objects.create(
        user=user,
        test=test_obj,
        classroom=classroom,
        test_type='regular',
        stage=stage,
        mode=mode or 'full_test',
        time_multiplier=time_multiplier or 1.0,
    ), True"""

if old_get_stage in views_content:
    views_content = views_content.replace(old_get_stage, new_get_stage)

# Fix module_test reordering
old_module_test = """    # получаем последовательность модулей
    sequence = get_test_sequence(test)

    if not sequence:
        return HttpResponse("Questions are not found")

    # получаем stage
    test_stage, created = _get_or_create_regular_test_stage(user, test, stage=1)"""

new_module_test = """    # получаем stage
    test_stage, created = _get_or_create_regular_test_stage(user, test, stage=1)

    # получаем последовательность модулей
    sequence = get_test_sequence(test, mode=test_stage.mode)

    if not sequence:
        return HttpResponse("Questions are not found")"""

if old_module_test in views_content:
    views_content = views_content.replace(old_module_test, new_module_test)

# Fix classroom_module_test reordering
old_classroom_module_test = """    user = request.user
    sequence = get_test_sequence(test)
    if not sequence:
        return HttpResponse('Questions are not found')

    test_stage, created = _get_or_create_regular_test_stage(user, test, stage=1, classroom=classroom)"""

new_classroom_module_test = """    user = request.user
    
    test_stage, created = _get_or_create_regular_test_stage(user, test, stage=1, classroom=classroom)

    sequence = get_test_sequence(test, mode=test_stage.mode)
    if not sequence:
        return HttpResponse('Questions are not found')"""

if old_classroom_module_test in views_content:
    views_content = views_content.replace(old_classroom_module_test, new_classroom_module_test)


# Fix get_test_sequence
old_get_sequence = """def get_test_sequence(test):
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
    )
    math_modules = set(
        Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    )
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
    return sequence"""

new_get_sequence = """def get_test_sequence(test, mode='full_test'):
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

if old_get_sequence in views_content:
    views_content = views_content.replace(old_get_sequence, new_get_sequence)

# Fix get_current_test_step and advance_test_stage
views_content = views_content.replace(
    "sequence = get_test_sequence(test_stage.test)",
    "sequence = get_test_sequence(test_stage.test, mode=test_stage.mode)"
)

# Fix _stage_attempt_is_complete
views_content = views_content.replace(
    "sequence = get_test_sequence(stage.test)",
    "sequence = get_test_sequence(stage.test, mode=stage.mode)"
)

with open(views_path, "w") as f:
    f.write(views_content)

print("Patch applied successfully.")
