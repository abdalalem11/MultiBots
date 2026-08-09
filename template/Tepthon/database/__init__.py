from .core.getdb import pyDatabase

#to import database 
jmdB = JmdB = pyDatabase()


#for old 
gvarstatus = jmdB.get_key
addgvar = jmdB.set_key
delgvar = jmdB.del_key 

#for something to store it 

InlinePlugin = {}
InlinePaths = []
CMD_HELP = {}
LIST = {}
