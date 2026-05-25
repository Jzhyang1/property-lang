from constants import Definition, PropertiesLookup, Scope, Expression, Property, Token
from definitions import register_definition, define_apply
import definitions

# We extend compilation
import llvmlite.ir as ir
from constants import Expression, Property, Scope
compile = globals()['definitions'].import_module(__file__, 'compile.py')

class StructureInstanceDefinition(Definition):
    # requires symbol = 'name_of_structure'
    # requires body = [field default values]
    @define_apply
    def apply(self, lhs: Expression, body: list[Expression]) -> Expression:
        return self.apply_(lhs, body)
    def apply_(self, lhs: Expression, body: list[Expression]) -> Expression:
        associated_value = {
            field.symbol.s: field for field in body
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
    @define_apply
    def apply(self, lhs: Expression) -> Expression:
        name_of_structure = self.properties[0].property.s
        structure_prop = lhs.force_get_property(name_of_structure)
        return structure_prop.associated_value[self.prop_symb]
    
class StructureFieldAssignmentDefinition(Definition):
    # Requires symbol = 'assign'
    # Requires property_names = ['name_of_structure', 'field_name']
    @define_apply
    def apply(self, lhs: Expression, rhs: Expression) -> Expression:
        name_of_structure = self.properties[0].property.s
        field_name = self.properties[1].property.s
        structure_prop = lhs.force_get_property(name_of_structure)
        structure_prop.associated_value[field_name] = rhs
        return rhs

@register_definition('structure', [], ['fields...'])
def structure(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    name = lhs.properties.pop().copy()    # The name of the structure is the last property of the expression
    for field in body:
        # Create the field definitions
        field_defn = StructureFieldDefinition(field.symbol.s, [name], False, [], [])
        scope.local_defns.setdefault(field.symbol.s, []).append(field_defn)
        assign_defn = StructureFieldAssignmentDefinition('assign', [name, Property(field.symbol)], False, [], [])
        scope.local_defns.setdefault('assign', []).append(assign_defn)
    # Create the structure definition
    struct_defn = StructureInstanceDefinition(name.property.s, [], True, [], body)
    scope.local_defns.setdefault(name.property.s, []).append(struct_defn)
    return struct_defn.apply_(lhs, body)
    
# Compilation

class CompileStructureInstanceDefinition(Definition):
    # Requires property_names = ['compile']
    # Requires symbol = 'name_of_structure'
    def __init__(self, *args, structure: ir.IdentifiedStructType, **kwargs):
        super().__init__(*args, **kwargs)
        self.structure = structure
    @define_apply
    def apply(self, lhs: Expression, body: list[Expression], scope: Scope, prop: Property) -> Expression:
        return self.apply_(lhs, body, scope, prop)
    def apply_(self, lhs: Expression, body: list[Expression], scope: Scope, prop: Property) -> Expression:
        # Generate the LLVM struct constant for the structure instance
        assert self.structure.elements is not None
        field_values = [compile.get_compiled(field, scope) for field in body]
        llvm_struct = ir.Constant(self.structure, field_values)
        compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=llvm_struct)
        return lhs.create_with_property(prop).replace_property('compiled_result', compiled_prop)

class CompileStructureFieldDefinition(Definition):
    # Requires property_names = ['compile', 'name_of_structure']
    # Requires symbol = 'name_of_field'
    def __init__(self, *args, field_index: int, field_type: Expression, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_index = field_index
        self.field_type = field_type
    @define_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
        res = builder.extract_value(compile.get_compiled(lhs, scope), self.field_index)
        prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
        
        name_of_struct = self.properties[-1].property.s
        lhs, _ = lhs.discard_properties_after(name_of_struct)
        lhs.properties += self.field_type.properties
        return lhs.replace_property('compiled_result', prop)
        
class CompileStructureFieldAssignmentDefinition(Definition):
    # Requires property_names = ['compile', 'structure', 'name_of_field']
    # Requires symbol = 'assign'
    def __init__(self, *args, field_index: int, field_type: Expression, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_index = field_index
        self.field_type = field_type
    @define_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
        struct_value = compile.get_compiled(lhs, scope)
        rhs_value = compile.get_compiled(rhs, scope)
        res = builder.insert_value(struct_value, rhs_value, self.field_index)
        prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
        return rhs.replace_property('compiled_result', prop)

@register_definition('structure', ['compile'], ['fields...'])
def compile_structure(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    name = lhs.properties.pop().copy()    # The name of the structure is the last property of the expression
    # We create a named LLVM struct type for the structure definition
    # and the CompileStructure Instance/FieldAccess/FieldAssignment definitions
    module: ir.Module = compile.get_compile_construct(scope, '__MODULE__')
    llvm_struct_type = module.context.get_identified_type(name.property.s)
    llvm_struct_type.set_body(*[compile.get_type(field, scope) for field in body])
    compile_prop = Property(name.property.create_renamed('compile'))
    for i, field in enumerate(body):
        field_name = field.symbol
        # Create the field definitions
        field_access_defn = CompileStructureFieldDefinition(field_name.s, [compile_prop, name], False, [], [], field_index=i, field_type=field)
        scope.local_defns.setdefault(field_name.s, []).append(field_access_defn)
        field_assign_defn = CompileStructureFieldAssignmentDefinition('assign', [compile_prop, name, Property(field_name)], False, [], [], field_index=i, field_type=field)
        scope.local_defns.setdefault('assign', []).append(field_assign_defn)
    # Create the structure instance definition
    instance_defn = CompileStructureInstanceDefinition(name, [compile_prop], False, [], [], structure=llvm_struct_type)
    scope.local_defns.setdefault(name.property.s, []).append(instance_defn)
    
    type_map: PropertiesLookup = compile.get_compile_construct(scope, '__TYPE_MAP__')
    type_map.exprs.append(compile.CompileTypeProperties(llvm_struct_type, [name]))
    return lhs