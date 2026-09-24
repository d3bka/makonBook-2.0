import re

views_path = "apps/sat/views.py"
with open(views_path, "r") as f:
    content = f.read()

content = content.replace(
    "def _required_modules_for_test(test_obj):",
    "def _required_modules_for_test(test_obj, mode='full_test'):"
)
content = content.replace(
    "return get_test_sequence(test_obj)",
    "return get_test_sequence(test_obj, mode=mode)"
)

old_calc_score = """def _calculate_attempt_score(user, test_obj, attempt_id, classroom=None):
    if not attempt_id:
        return None

    required_modules = _required_modules_for_test(test_obj)"""
new_calc_score = """def _calculate_attempt_score(user, test_obj, attempt_id, classroom=None):
    if not attempt_id:
        return None

    stage = TestStage.objects.filter(user=user, test=test_obj, attempt_id=attempt_id).first()
    mode = stage.mode if stage else 'full_test'
    required_modules = _required_modules_for_test(test_obj, mode=mode)"""
content = content.replace(old_calc_score, new_calc_score)

old_completed = """def _completed_attempt_ids_from_modules(user, test_obj, classroom=None):
    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return []

    required_slots = {
        (_normalize_test_section(section), _normalize_test_module(module))
        for section, module in required_modules
    }
    slots_by_attempt = defaultdict(set)
    latest_time_by_attempt = {}

    modules = TestModule.objects.filter(
        user=user,
        test=test_obj,
        test_type='regular',
        attempt_id__isnull=False,
        **_classroom_scope_filter(classroom),
    ).only('attempt_id', 'section', 'module', 'created_at', 'created')

    for module_obj in modules:
        attempt_id = module_obj.attempt_id
        if not attempt_id:
            continue

        slot = (
            _normalize_test_section(module_obj.section),
            _normalize_test_module(module_obj.module),
        )
        slots_by_attempt[attempt_id].add(slot)

        module_time = module_obj.created_at or module_obj.created
        if module_time and (
            attempt_id not in latest_time_by_attempt or
            module_time > latest_time_by_attempt[attempt_id]
        ):
            latest_time_by_attempt[attempt_id] = module_time

    fallback_time = timezone.now() - timedelta(days=36500)
    completed_attempt_ids = [
        attempt_id
        for attempt_id, slots in slots_by_attempt.items()
        if required_slots.issubset(slots)
    ]
    completed_attempt_ids.sort(
        key=lambda attempt_id: latest_time_by_attempt.get(attempt_id) or fallback_time,
        reverse=True,
    )
    return completed_attempt_ids"""

new_completed = """def _completed_attempt_ids_from_modules(user, test_obj, classroom=None):
    modules = TestModule.objects.filter(
        user=user,
        test=test_obj,
        test_type='regular',
        attempt_id__isnull=False,
        **_classroom_scope_filter(classroom),
    ).only('attempt_id', 'section', 'module', 'created_at', 'created')

    slots_by_attempt = defaultdict(set)
    latest_time_by_attempt = {}

    for module_obj in modules:
        attempt_id = module_obj.attempt_id
        if not attempt_id:
            continue
        slot = (
            _normalize_test_section(module_obj.section),
            _normalize_test_module(module_obj.module),
        )
        slots_by_attempt[attempt_id].add(slot)
        module_time = module_obj.created_at or module_obj.created
        if module_time and (
            attempt_id not in latest_time_by_attempt or
            module_time > latest_time_by_attempt[attempt_id]
        ):
            latest_time_by_attempt[attempt_id] = module_time

    if not slots_by_attempt:
        return []

    stages = TestStage.objects.filter(attempt_id__in=slots_by_attempt.keys())
    mode_by_attempt = {s.attempt_id: s.mode for s in stages}

    fallback_time = timezone.now() - timedelta(days=36500)
    completed_attempt_ids = []
    
    for attempt_id, slots in slots_by_attempt.items():
        mode = mode_by_attempt.get(attempt_id, 'full_test')
        req_modules = _required_modules_for_test(test_obj, mode=mode)
        if not req_modules:
            continue
        required_slots = {
            (_normalize_test_section(section), _normalize_test_module(module))
            for section, module in req_modules
        }
        if required_slots.issubset(slots):
            completed_attempt_ids.append(attempt_id)
            
    completed_attempt_ids.sort(
        key=lambda attempt_id: latest_time_by_attempt.get(attempt_id) or fallback_time,
        reverse=True,
    )
    return completed_attempt_ids"""
content = content.replace(old_completed, new_completed)

old_results = """    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return HttpResponse("Questions are not found", status=404)

    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review, classroom=classroom)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id, classroom=classroom)"""
new_results = """    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review, classroom=classroom)
    
    stage = TestStage.objects.filter(user=user, test=test_obj, attempt_id=attempt_id).first()
    mode = stage.mode if stage else 'full_test'

    required_modules = _required_modules_for_test(test_obj, mode=mode)
    if not required_modules:
        return HttpResponse("Questions are not found", status=404)

    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id, classroom=classroom)"""
content = content.replace(old_results, new_results)

old_cert = """def _generate_certificate_response(user, test_obj, testreview):
    test_mode = get_test_mode(test_obj)
    required_modules = _required_modules_for_test(test_obj)"""
new_cert = """def _generate_certificate_response(user, test_obj, testreview):
    test_mode = get_test_mode(test_obj)
    stage = TestStage.objects.filter(user=user, test=test_obj, attempt_id=testreview.attempt_id).first()
    mode = stage.mode if stage else 'full_test'
    required_modules = _required_modules_for_test(test_obj, mode=mode)"""
content = content.replace(old_cert, new_cert)

with open(views_path, "w") as f:
    f.write(content)

