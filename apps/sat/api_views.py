import json
from django.http import JsonResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.sat.models import Test
from apps.sat.views import _get_or_create_regular_test_stage

_PTC_VALID_MODES = {'full_test', 'rw_only', 'math_only', 'single_english', 'single_math'}
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
