if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, multi_apply, CompileError

# We extend compilation
import llvmlite.ir as ir

from constants import Expression, Property, Scope
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")

class StructureInstanceDefinition(Definition):
    # requires symbol = 'name_of_structure'
    # requires body = [field default values]
    @multi_apply
    def apply(self, lhs: Expression, fields: list[Expression], scope: Scope) -> Expression:
        return self.apply_(lhs, fields)
    def apply_(self, lhs: Expression, fields: list[Expression]) -> Expression:
        associated_value = {
            field.symbol.s: field for field in fields
        }
        # For unspecified fields, we use the default value from the structure definition
        for expr in self.body:
            if expr.symbol.s not in associated_value:
                associated_value[expr.symbol.s] = expr.copy()
        prop = Property(lhs.symbol.create_renamed(self.prop_symb), is_association=True, associated_value=associated_value)
        return lhs.create_with_property(prop)

class StructureFieldDefinition(Definition):
    # Requires symbol = 'name_of_field'
    # Requires property_names = ['name_of_structure']
    @unary_apply
    def apply(self, lhs: Expression, scope: 'Scope') -> Expression:
        name_of_structure = self.properties[0].property.s
        structure_prop = lhs.force_get_property(name_of_structure)
        return structure_prop.associated_value[self.prop_symb]
    
class StructureFieldAssignmentDefinition(Definition):
    symbol = 'assign'
    # Requires property_names = ['name_of_structure', 'field_name']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: 'Scope') -> Expression:
        name_of_structure = self.properties[0].property.s
        field_name = self.properties[1].property.s
        structure_prop = lhs.force_get_property(name_of_structure)
        structure_prop.associated_value[field_name] = rhs
        return rhs

@builtin_definition
class StructureDefinition(Definition):
    # Creates a named structure definition
    symbol = 'structure'
    param_names = ['fields...']
    @multi_apply
    def apply(self, lhs: Expression, fields: list[Expression], scope: Scope) -> Expression:
        lhs = lhs.copy()
        name = lhs.properties.pop().copy()    # The name of the structure is the last property of the expression
        for field in fields:
            # Create the field definitions
            field_defn = StructureFieldDefinition(field.symbol.s, [name], False, [], [])
            scope.local_defns.setdefault(field.symbol.s, []).append(field_defn)
            assign_defn = StructureFieldAssignmentDefinition('assign', [name, Property(field.symbol)], False, [], [])
            scope.local_defns.setdefault('assign', []).append(assign_defn)
        # Create the structure definition
        struct_defn = StructureInstanceDefinition(name.property.s, [], True, [], fields)
        scope.local_defns.setdefault(name.property.s, []).append(struct_defn)
        return struct_defn.apply_(lhs, fields)
    
# Compilation

class CompileStructureInstanceDefinition(Definition):
    symbol = 'compile'
    # Requires property_names = ['name_of_structure']
    def __init__(self, *args, structure: ir.IdentifiedStructType, **kwargs):
        super().__init__(*args, **kwargs)
        self.structure = structure
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        return self.apply_(lhs, scope)
    def apply_(self, lhs: Expression, scope: Scope) -> Expression:
        name_of_struct = self.properties[0].property.s
        struct_prop = lhs.force_get_property(name_of_struct)
        fields = struct_prop.compound_properties
        # Generate the LLVM struct constant for the structure instance
        assert self.structure.elements is not None
        field_values = [compile.get_compiled(field, scope) for field in fields]
        llvm_struct = ir.Constant(self.structure, field_values)
        prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=llvm_struct)
        return lhs.replace_property('compile', prop)

class CompileStructureFieldDefinition(Definition):
    symbol = 'compile'
    # Requires property_names = ['name_of_structure', 'name_of_field']
    def __init__(self, *args, field_index: int, field_type: Expression, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_index = field_index
        self.field_type = field_type
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
        res = builder.extract_value(compile.get_compiled(lhs, scope), self.field_index)
        prop = Property(lhs.symbol.create_renamed(f'compile'), is_association=True, associated_value=res)
        
        name_of_struct = self.properties[0].property.s
        lhs, _ = lhs.discard_properties_after(name_of_struct)
        lhs.properties += self.field_type.properties
        return lhs.replace_property('compile', prop)
        
class CompileStructureFieldAssignmentDefinition(Definition):
    symbol = 'compile'
    # requires property_names = ['structure', 'name_of_field', 'assign']
    def __init__(self, *args, field_index: int, field_type: Expression, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_index = field_index
        self.field_type = field_type
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
        lhs, assign_prop = lhs.discard_properties_after('assign')
        struct_value = compile.get_compiled(lhs, scope)
        if len(assign_prop.compound_properties) != 1:
            raise CompileError("field assignment must have exactly one compound property", anchor=assign_prop.property)
        rhs_expr = assign_prop.compound_properties[0]
        rhs_value = compile.get_compiled(rhs_expr, scope)
        res = builder.insert_value(struct_value, rhs_value, self.field_index)
        prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', prop)

@builtin_definition
class CompileStructureDefinition(Definition):
    symbol = 'compile'
    property_names = ['structure']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, struct_prop = lhs.discard_properties_after('structure')
        fields = struct_prop.compound_properties
        name = lhs.properties.pop().copy()    # The name of the structure is the last property of the expression
        # We create a named LLVM struct type for the structure definition
        # and the CompileStructure Instance/FieldAccess/FieldAssignment definitions
        module: ir.Module = compile.get_compile_construct(scope, '__MODULE__')
        llvm_struct_type = module.context.get_identified_type(name.property.s)
        llvm_struct_type.set_body(*[compile.get_type(field, scope) for field in fields])
        for i, field in enumerate(fields):
            field_name = field.symbol
            # Create the field definitions
            field_access_defn = CompileStructureFieldDefinition('compile', [name, Property(field_name)], False, [], [], field_index=i, field_type=field)
            scope.local_defns.setdefault('compile', []).append(field_access_defn)
            field_assign_defn = CompileStructureFieldAssignmentDefinition('compile', [name, Property(field_name), Property(field_name.create_renamed('assign'))], False, [], [], field_index=i, field_type=field)
            scope.local_defns.setdefault('compile', []).append(field_assign_defn)
        # Create the structure instance definition
        instance_defn = CompileStructureInstanceDefinition('compile', [name], False, [], [], structure=llvm_struct_type)
        scope.local_defns.setdefault('compile', []).append(instance_defn)
        
        type_map = compile.get_compile_construct(scope, '__TYPE_MAP__')
        type_map[name.property.s] = llvm_struct_type
        return lhs