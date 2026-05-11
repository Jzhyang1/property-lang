if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, multi_apply, create_list, CompileError

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
        print(name_of_structure, structure_prop.associated_value)
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
        return lhs.create_with_property(Property(name.property, is_association=True, associated_value={field.symbol.s: field for field in fields}))