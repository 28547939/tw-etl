import logging
import asyncio
import argparse
import sys

from stream_manager import manager

async def main():

    prs=argparse.ArgumentParser(
        prog='',
        description='',
    )

    prs.add_argument('--config', required=True)

    # for now, no need for either the 'resume' or 'no-resume' options. if the user does
    # not want to resume from existing state, it should be deleted or moved aside (since it
    # will be immediately overwritten anyway once the program initializes its own state)
    #prs.add_argument('--no-resume', default=False, action='store_true')
    args=vars(prs.parse_args())


    fmt=logging.Formatter(
        # TODO having issues with taskName
        #fmt='[%(taskName)s][%(asctime)s] %(message)s',
        fmt='[%(asctime)s] %(message)s',
        datefmt='%Y-%m-%d_%H-%M-%S.%f',
        #defaults={
        #    'taskName': 'main'
        #}
    ) 
    logger=logging.getLogger('stream_manager')
    logger.setLevel(logging.DEBUG)
    h=logging.StreamHandler(stream=sys.stdout)
    h.setFormatter(fmt)
    logger.addHandler(h)

    h=logging.StreamHandler(stream=sys.stderr)
    h.setLevel(logging.ERROR)
    logger.addHandler(h)

    i = manager.manager(args['config'], logger)
    #await i.start(args['no_resume'])
    await i.start()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
