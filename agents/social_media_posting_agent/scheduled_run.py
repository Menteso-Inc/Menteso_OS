"""Read-only connection monitoring; never invokes a publishing worker."""
import json
from .runtime import monitor


def main():
    result=monitor()
    print(json.dumps({'checked_at':result['checked_at'],'publishing_enabled':result['publishing_enabled'],
        'connections':{name:value.get('connected',False) for name,value in result['platforms'].items()},'posts_published':0}))


if __name__=='__main__':main()
