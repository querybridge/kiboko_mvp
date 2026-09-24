# MySQL driver: use PyMySQL (pure-Python) as the MySQLdb backend. mysqlclient
# can't compile on the local Homebrew Python, and PyMySQL works identically on
# local + PythonAnywhere. Django's mysql backend requires mysqlclient>=1.4.3, so
# spoof the reported version before registering PyMySQL as MySQLdb.
try:
    import pymysql
    pymysql.version_info = (1, 4, 6, 'final', 0)
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
