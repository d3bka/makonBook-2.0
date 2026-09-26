import re
import time

timestamp = str(int(time.time()))

def bust_cache(filepath):
    with open(filepath, "r") as f:
        html = f.read()
    
    # Replace already versioned css links
    html = re.sub(
        r"(href=\"\{\% static 'assets/css/([^']+)\.css' \%\}\?v=[^\"]+\")",
        lambda m: re.sub(r"\?v=[^\"]+", f"?v={timestamp}", m.group(1)),
        html
    )

    with open(filepath, "w") as f:
        f.write(html)

bust_cache("templates/test/shared/attempt_math.html")
bust_cache("templates/test/shared/attempt_eng.html")
