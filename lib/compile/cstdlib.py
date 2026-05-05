import llvmlite.ir as ir

# stdlib

def define_malloc(module):
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.IntType(64)]), name="malloc")
def define_free(module):
    ir.Function(module, ir.FunctionType(ir.VoidType(), [ir.PointerType(ir.IntType(8))]), name="free")

# stdio

def define_printf(module):
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))], var_arg=True), name="printf")
def define_puts(module):
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))]), name="puts")

# string

def define_strcmp(module):
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strcmp')
def define_strcpy(module):
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strcpy')
def define_strcat(module):
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strcat')
def define_strlen(module):
    ir.Function(module, ir.FunctionType(ir.IntType(64), [ir.PointerType(ir.IntType(8))]), name='strlen')