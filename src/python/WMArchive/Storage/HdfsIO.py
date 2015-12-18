#!/usr/bin/env python
#-*- coding: utf-8 -*-
#pylint: disable=
"""
File       : HdfsIO.py
Author     : Valentin Kuznetsov <vkuznet AT gmail dot com>
Description: WMArchive HDFS storage module based on pydoop python module
    pydoop HDFS docs:
    http://crs4.github.io/pydoop/api_docs/hdfs_api.html#hdfs-api
    http://crs4.github.io/pydoop/tutorial/hdfs_api.html#hdfs-api-tutorial
    http://stackoverflow.com/questions/23614588/encode-an-object-with-avro-to-a-byte-array-in-python

    python gzip: https://docs.python.org/2/library/gzip.html
    python io: https://docs.python.org/2/library/io.html

    Usage of GzipFile with file-like object, e.g. io.BytesIO
    http://stackoverflow.com/questions/4204604/how-can-i-create-a-gzipfile-instance-from-the-file-like-object-that-urllib-url
"""

# futures
from __future__ import print_function, division

# system modules
import os
import io
import gzip
import itertools
from types import GeneratorType

# avro modules
import avro.schema
import avro.io

# hdfs pydoop modules
import pydoop.hdfs as hdfs

# WMArchive modules
from WMArchive.Storage.BaseIO import Storage
from WMArchive.Utils.Utils import tstamp, wmaHash
from WMArchive.Utils.Regexp import PAT_UID

def fileName(uri, wmaid, compress):
    "Construct common file name"
    if  compress:
        return '%s/%s.avro.gz' % (uri, wmaid)
    return '%s/%s.avro' % (uri, wmaid)

class HdfsStorage(Storage):
    "Storage based on Hdfs back-end"
    def __init__(self, uri, compress=False):
        "ctor with hdfs uri: hdfsio:/path/schema.avsc"
        Storage.__init__(self, uri)
        schema = self.uri
        if  not hdfs.ls(schema):
            raise Exception("No avro schema file found in provided uri: %s" % uri)
        self.hdir = self.uri.rsplit('/', 1)[0]
        if  not hdfs.path.isdir(hdir):
            raise Exception('HDFS path %s does not exists' % self.hdir)
        schemaData = hdfs.load(schema)
        self.schema = avro.schema.parse(schemaData)
        self.compress = compress

    def _write(self, rec):
        "Internal Write API"
        wmaid = rec['wmaid']
        fname = fileName(self.hdir, wmaid, self.compress)

        # create Avro writer and binary encoder
        writer = avro.io.DatumWriter(self.schema)
        bytes_writer = io.BytesIO()

        if  self.compress:
            # use gzip'ed writer with BytesIO file object
            gzip_writer = gzip.GzipFile(fileobj=bytes_writer, mode='wb')
            encoder = avro.io.BinaryEncoder(gzip_writer)
        else:
            # plain binary reader
            encoder = avro.io.BinaryEncoder(bytes_writer)

        # write records from given data stream to binary writer
        writer.write(rec, encoder)

        # close gzip stream if necessary
        if  self.compress:
            gzip_writer.flush()
            gzip_writer.close()

        # store raw data to hadoop via HDFS
        hdfs.dump(bytes_writer.getvalue(), fname)

    def _read(self, query=None):
        "Internal read API"
        if  PAT_UID.match(str(query)): # requested to read concrete file
            out = []
            fname = fileName(self.hdir, query, self.compress)
            data = hdfs.load(fname)

            if  self.compress:
                # use gzip'ed reader and pass to it BytesIO as file object
                gzip_reader = gzip.GzipFile(fileobj=io.BytesIO(data))
                decoder = avro.io.BinaryDecoder(gzip_reader)
            else:
                # use non-compressed reader
                bytes_reader = io.BytesIO(data)
                decoder = avro.io.BinaryDecoder(bytes_reader)

            reader = avro.io.DatumReader(self.schema)
            while True:
                try:
                    rec = reader.read(decoder)
                    out.append(rec)
                except:
                    break
            return out
        return self.empty_data
