"""Project-wide setup that must run before Django loads any app code."""

import pymysql

# django.db.backends.mysql is written against mysqlclient (the MySQLdb
# API) and checks Database.version_info against a minimum it recognizes.
# PyMySQL is a pure-Python driver with no compiled extension or
# libmysqlclient-dev headers to install; faking its version and registering
# it as MySQLdb here (before Django imports it) lets django.db.backends.mysql
# use it transparently. See:
# https://adamj.eu/tech/2020/02/04/how-to-use-pymysql-with-django/
pymysql.version_info = (2, 2, 4, "final", 0)
pymysql.install_as_MySQLdb()
