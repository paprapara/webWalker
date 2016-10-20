# -*- coding: utf-8 -*-
import json
import os
import traceback

import openpyxl
from scrapy import Item
from scrapy.signals import spider_closed

from spiders.constant import ITEM_FIELD
from spiders.utils import Logger


class BasePipeline(Logger):
    fileobj = None

    def __init__(self, settings):
        self.set_logger(self.crawler)

    @classmethod
    def from_crawler(cls, crawler):
        cls.crawler = crawler
        o =  cls(crawler.settings)
        crawler.signals.connect(o.spider_closed, signal=spider_closed)
        return o

    def spider_closed(self):
        if self.fileobj:
            self.logger.info("close file buffer...")
            self.fileobj.close()


class LoggingBeforePipeline(BasePipeline):

    '''
    Logs the crawl, currently the 1st priority of the pipeline
    '''

    def __init__(self, settings):
        super(LoggingBeforePipeline, self).__init__(settings)
        self.logger.debug("Setup before pipeline")


    def process_item(self, item, spider):
        self.logger.debug("Processing item in LoggingBeforePipeline")
        if isinstance(item, spider.base_item_cls):
            self.logger.debug('Scraped page')
            return item
        elif isinstance(item, Item):
            self.logger.error('Scraper Retry')
            return None


class ExcelPipeline(BasePipeline):
    '''
       Logs the crawl for successfully pushing to Kafka
       '''

    def __init__(self, settings):
        super(ExcelPipeline, self).__init__(settings)
        self.logger.debug("Setup file pipeline")
        self.excels = {}
        self.title = None
        self.setup()

    def create_excel(self, crawlid):
        file_name = "task/%s_%s.xlsx" % (self.crawler.spidercls.name, crawlid)
        wb = openpyxl.Workbook()
        fileobj = wb.active
        fileobj.title = u"数据统计"
        line = 1
        line = self.write_title(fileobj, line)
        self.excels.setdefault(file_name, []).append(wb)
        self.excels[file_name].append(fileobj)
        self.excels[file_name].append(line)
        return wb, fileobj, line

    def _yield_alpha(self):
        index = 0
        staffix = ""
        while True:
            yield self._gen(index, staffix)
            index += 1

    def _gen(self, index, staffix):
        div, mod = divmod(index, 26)
        if div == 0:
            return chr(65+mod) + staffix
        else:
            return self._gen(div-1, chr(65 + mod)+staffix)

    def setup(self):
        if not os.path.exists("task"):
            os.mkdir("task")
        self.title = self.title or\
                     map(lambda x: x[0], ITEM_FIELD[self.crawler.spidercls.name])

    def write_title(self, fileobj, line):
        column_alp = self._yield_alpha()
        for field in self.title:
            fileobj["%s%s"%(column_alp.next(), line)] = field
        line += 1
        return line

    def process_item(self, item, spider):
        self.logger.debug("Processing item in ExcelPipeline")
        if isinstance(item, spider.base_item_cls):
            try:
                crawlid = item["crawlid"]
                file_name  = "task/%s_%s.xlsx"%(spider.name, crawlid)
                wb, fileobj, line = self.excels.get(file_name) or self.create_excel(crawlid)
                column_alp = self._yield_alpha()
                for field in self.title:
                    fileobj["%s%s" % (column_alp.next(), line)] = str(item[field])
                item["success"] = True
                self.excels[file_name][2] = line + 1
            except Exception:
                self.logger.error(traceback.format_exc())
                item["success"] = False
        return item

    def spider_closed(self):
        self.logger.info("close excel...")
        for file_name, meta in self.excels.items():
            meta[0].save(file_name)


class JSONPipeline(BasePipeline):
    '''
       Logs the crawl for successfully pushing to Kafka
       '''

    def __init__(self, settings):
        super(JSONPipeline, self).__init__(settings)
        self.logger.debug("Setup file pipeline")
        if not os.path.exists("task"):
            os.mkdir("task")
        self.fileobj = open("task/result.json", "w")
        self.fileobj.write("[")

    def process_item(self, item, spider):
        self.logger.debug("Processing item in FilePipeline")
        if isinstance(item, spider.base_item_cls):
            self.fileobj.write("%s,\n"%json.dumps(dict(item)))
            item["success"] = True
        return item

    def spider_closed(self):
        self.logger.info("close file...")
        try:
            self.fileobj.seek(-2, 1)
            self.fileobj.write("]")
        except IOError:
            pass
        self.fileobj.close()


class LoggingAfterPipeline(BasePipeline):

    '''
    Logs the crawl for successfully pushing to Kafka
    '''

    def __init__(self, settings):
        super(LoggingAfterPipeline, self).__init__(settings)
        self.logger.debug("Setup after pipeline")

    def process_item(self, item, spider):
        self.logger.debug("Processing item in LoggingAfterPipeline")
        if isinstance(item, spider.base_item_cls):
            # make duplicate item, but remove unneeded keys
            if item['success']:
                self.logger.debug('Sent page to Kafka')
            else:
                self.logger.error('failed send to Kafka')
            return item
