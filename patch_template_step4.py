import re

html_path = "templates/sat/practice_tests.html"
with open(html_path, "r") as f:
    html = f.read()

old_action = """                  {% elif classroom %}
                    <a
                      href="{% url 'classroom_practise' classroom.id test.name %}"
                      class="practice-action"
                      data-practice-navigate
                    >
                      <span>{{ test.action_label }}</span>
                      <i class="bi bi-arrow-right" aria-hidden="true"></i>
                    </a>
                  {% else %}
                    <a
                      href="{% url 'practise' test.name %}"
                      class="practice-action"
                      data-practice-navigate
                    >
                      <span>{{ test.action_label }}</span>
                      <i class="bi bi-arrow-right" aria-hidden="true"></i>
                    </a>
                  {% endif %}"""

new_action = """                  {% elif classroom %}
                    <a
                      href="{% url 'classroom_practise' classroom.id test.name %}"
                      class="practice-action"
                      {% if test.card_state != 'continue' %}data-practice-navigate{% endif %}
                    >
                      <span>{{ test.action_label }}</span>
                      <i class="bi bi-arrow-right" aria-hidden="true"></i>
                    </a>
                  {% else %}
                    <a
                      href="{% url 'practise' test.name %}"
                      class="practice-action"
                      {% if test.card_state != 'continue' %}data-practice-navigate{% endif %}
                    >
                      <span>{{ test.action_label }}</span>
                      <i class="bi bi-arrow-right" aria-hidden="true"></i>
                    </a>
                  {% endif %}"""

html = html.replace(old_action, new_action)

with open(html_path, "w") as f:
    f.write(html)
