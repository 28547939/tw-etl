import logging
import asyncio
import argparse

from stream_manager import manager

async def main():

    prs=argparse.ArgumentParser(
        prog='',
        description='',
    )

    prs.add_argument('--config', required=True)
    prs.add_argument('--resume', default=False, action='store_true')
    prs.add_argument('--errorlog')
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
    logger=logging.getLogger('tw')
    logger.setLevel(logging.DEBUG)
    h=logging.StreamHandler()
    h.setFormatter(fmt)
    logger.addHandler(h)

    if 'errorlog' in args:
        h=logging.FileHandler(args['errorlog'])
        h.setLevel(logging.ERROR)
        logger.addHandler(h)


    i = manager(args['config'], logger, args['resume'])
    await i.start()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
