from configparser import ConfigParser, SectionProxy

from locale import getlocale
from pathlib import Path
from os import access, W_OK


class LocaleString:
    def __init__(self, raw_string: str):
        split_by_mod = raw_string.split('@')
        self.modifier = split_by_mod[1] if len(split_by_mod) > 1 else None
        split_by_cnt = split_by_mod[0].split('_')
        self.country = split_by_cnt[1] if len(split_by_cnt) > 1 else None
        self.lang = split_by_cnt[0]

        if not self.lang:
            raise ValueError('LocaleString must contain a language to be defined')

    def find_closest(self, candidates: list['LocaleString']) -> 'LocaleString':
        if len(candidates) > 0:
            closeness: list[int] = [0 for _ in candidates] # Higher is better

            for i, l in enumerate(candidates):
                not_valid_flag = False

                if l.lang:
                    if self.lang == l.lang:
                        closeness[i] += 1
                    else:
                        not_valid_flag = True
                if l.country:
                    if self.country == l.country:
                        closeness[i] += 4
                    else:
                        not_valid_flag = True
                if l.modifier:
                    if self.modifier == l.modifier:
                        closeness[i] += 2
                    else:
                        not_valid_flag = True

                if not_valid_flag:
                    closeness[i] = 0
            
            if max(closeness) > 0:
                return candidates[closeness.index(max(closeness))]


    def __str__(self):
        return self.lang + \
            (f'_{self.country}' if self.country else '') + \
            (f'@{self.modifier}' if self.modifier else '')

    def __repr__(self):
        return f'<LocaleString {self.__str__()}>'

class Field:
    '''
    A field in a DesktopFile
    It handles type convertion and localization
    '''

    def __init__(self, key: str, section: SectionProxy) -> None:
        self.key = key
        self.section = section

        self.unlocalized_key: str = self.key.split('[')[0]
        self.locale: str = self.key.split('[')[1].removesuffix(']') if '[' in self.key else None

    @staticmethod
    def list_from_section(section: SectionProxy) -> list['Field']:
        unlocalized_keys = list(filter(
            lambda k: '[' not in k,
            section.keys()))

        return [Field(k, section) for k in unlocalized_keys]
    @staticmethod
    def dict_from_section(section: SectionProxy) -> dict[str, 'Field']:
        unlocalized_keys = list(filter(
            lambda k: '[' not in k,
            section.keys()))

        return {k: Field(k, section) for k in unlocalized_keys}

    @property
    def _value(self) -> str: return self.section.get(self.key)

    @property
    def localized_fields(self) -> list['Field']:
        return [
            Field(k, self.section) \
            for k in self.section.keys() \
            if k.startswith(f'{self.unlocalized_key}[') \
            and k != self.unlocalized_key]

    def get(self, locale: str = None) -> 'bool | int | float | list[str] | str | None':
        field = self.localize(locale) if locale != None else self
        
        if field.as_bool() != None: return field.as_bool()
        elif field.as_int() != None: return field.as_int()
        elif field.as_float() != None: return field.as_float()
        elif field.as_str_list() != None: return field.as_str_list()
        else: 
            return field.as_str()

    def set(self, new_value: 'bool | int | float | list[str] | str', create_non_existing_key = True):
        print(f'Setting {self.key} to {new_value}')

        if isinstance(new_value, bool):
            new_str_value = 'true' if new_value else 'false'
        elif isinstance(new_value, list):
            new_value = [str(i) for i in new_value]
            new_str_value = ';'.join(new_value) + ';'
        else:
            new_str_value = str(new_value)

        if self.key in self.section.keys() or create_non_existing_key:
            self.section.parser.set(self.section.name, self.key, new_str_value)
        else:
            raise KeyError('Cannot set a non-existing key')

    def remove(self):
        self.section.parser.remove_option(self.section.name, self.key)

    def localize(self, 
        locale: str = None, 
        strict = False, 
        auto_localize_if_no_locale = True,
        return_unlocalized_as_fallback = True,
        return_non_existing_key_as_fallback = False) -> 'Field':
        '''If the field has localizations, returns the most similar one. If not given, returns the system locale.'''

        if strict:
            auto_localize_if_no_locale = False
            return_unlocalized_as_fallback = False
            return_non_existing_key_as_fallback = False

        # If locale is not given, gets the system locale
        if locale == None:
            if auto_localize_if_no_locale:
                locale = getlocale()[0]
            else:
                raise TypeError(f'Localization string cannot be None')
        
        # Finds the closest locale to the one specified from the localizations
        key_locales: list[str] = [LocaleString(f.locale) for f in self.localized_fields]
        
        closest_locale = LocaleString(locale).find_closest(key_locales)

        # If no close locale is found, returns the unlocalized version of itself
        if closest_locale != None:
            return Field(f'{self.unlocalized_key}[{closest_locale}]', self.section)
        elif return_unlocalized_as_fallback:
            return Field(self.unlocalized_key, self.section)
        elif return_non_existing_key_as_fallback:
            return Field(f'{self.unlocalized_key}[{locale}]', self.section)
        else:
            raise ValueError(f'{self.__repr__()} cannot be localized as \'{locale}\'')
    
    def exists(self) -> bool:
        return self._value != None

    def as_bool(self, strict = False) -> 'bool | None':
        if self.exists():
            if self._value.lower() == 'true':
                return True
            elif self._value.lower() == 'false':
                return False
        
        if strict:
            raise ValueError(f'{self.__repr__()} cannot be converted to bool')

    def as_int(self, strict = False):
        if self.exists():
            if self._value.isdecimal():
                return int(self._value)

        if strict:
            raise ValueError(f'{self.__repr__()} cannot be converted to int')

    def as_float(self, strict = False):
        try: 
            return float(self._value)
        except (ValueError, TypeError):
            if strict:
                raise ValueError(f'{self.__repr__()} cannot be converted to float')

    def as_str_list(self, strict = False) -> 'list[str] | None':
        if self.exists():
            if self._value.strip().endswith(';'):
                return self._value.split(';')[:-1]
        
        if strict:
            raise ValueError(f'{self.__repr__()} cannot be converted to list[str]')

    def as_str(self, strict = False) -> str:
        if self.exists():
            return str(self._value)
        elif strict:
            raise ValueError(f'{None} cannot be converted to str')

    def __getitem__(self, value: str):
        return self.localize(locale=value, return_unlocalized_as_fallback=False, return_non_existing_key_as_fallback=True)


    def __bool__(self) -> bool: return self.as_bool(strict=True)
    def __int__(self) -> int: return self.as_int(strict=True)
    def __float__(self) -> float: return self.as_float(strict=True)
    def __list__(self) -> list: return self.as_str_list(strict=True)
    def __str__(self) -> str: return self.as_str() or str(None)
    def __repr__(self) -> str: return f'<Desktop entry field \'{self.key}\'>'


class Section:
    def __init__(self, section: SectionProxy):
        self.section = section

    def section_name(self) -> str: 
        return self.section.name

    def add_entry(self, key, value):
        Field(key, self.section).set(value)

    def add_field(self, field: Field):
        self.add_entry(field.key, field._value)

    def __getattr__(self, name) -> 'Field':
        return Field(name, self.section)

    def keys(self): return self.as_dict().keys()
    def items(self): return self.as_dict().items()
    def values(self): return self.as_dict().values()
    def as_dict(self): return {k: Field(k, self.section) for k, v in self.section.items()}

class AppSection(Section):
    NAME = 'Desktop Entry'
    RECOGNIZED_KEYS = [
        'NoDisplay',
        'Hidden',
        'DBusActivatable',
        'Terminal',
        'StartupNotify',
        'PrefersNonDefaultGPU',
        'SingleMainWindow',
        'Type',
        'Exec',
        'Icon',
        'Version',
        'TryExec',
        'Path',
        'StartupWMClass',
        'URL',
        'OnlyShowIn',
        'NotShowIn',
        'Actions',
        'MimeType',
        'Categories',
        'Implements',
        'Name',
        'GenericName',
        'Comment',
        'Keywords',]

    NoDisplay: Field
    Hidden: Field
    DBusActivatable: Field
    Terminal: Field
    StartupNotify: Field
    PrefersNonDefaultGPU: Field
    SingleMainWindow: Field
    Type: Field
    Exec: Field
    Icon: Field
    Version: Field
    TryExec: Field
    Path: Field
    StartupWMClass: Field
    URL: Field
    OnlyShowIn: Field
    NotShowIn: Field
    Actions: Field
    MimeType: Field
    Categories: Field
    Implements: Field
    Name: Field
    GenericName: Field
    Comment: Field
    Keywords: Field

    @classmethod
    def from_parser(self, parser: ConfigParser) -> 'AppSection':
        if self.NAME not in parser.sections():
            parser.add_section(self.NAME)
        
        return AppSection(parser[self.NAME])

    def __init__(self, section: SectionProxy):
        super().__init__(section)

    def is_recognized(self, key: str):
        return key in self.RECOGNIZED_KEYS

class ActionSection(Section):
    PREFIX = 'Desktop Action'
    RECOGNIZED_KEYS = [
        'Name',
        'Exec',]

    Name: Field
    Exec: Field

    @classmethod
    def list_from_parser(self, parser: ConfigParser) -> list['ActionSection']:
        return [
            ActionSection(parser[section_name]) \
            for section_name in parser.sections() \
            if section_name.startswith(self.PREFIX)]

    @classmethod
    def dict_from_parser(self, parser: ConfigParser) -> dict[str, 'ActionSection']:
        return {
            action_section.action_name(): action_section \
            for action_section in ActionSection.list_from_parser(parser)}

    def __init__(self, section: SectionProxy) -> None:
        super().__init__(section)

    def action_name(self) -> str: 
        return self.section_name().removeprefix(self.PREFIX).strip()


class IniFile:
    def __init__(self, path: 'str | Path') -> None:
        self.path = Path(path)
        self.is_loaded = False

        self.parser = ConfigParser(interpolation=None, )
        self.parser.optionxform=str

    @property
    def filename(self) -> str: return self.path.name

    def load(self):
        self.parser.clear()
        self.parser.read(self.path)
        self.is_loaded = True

    def filter(self, filter: callable) -> None:
        '''Applies `filter()` to all values of the file, and only keeps values for wich it returns True'''
        for section_name, section in self.parser.items():
                for k, v in section.items():
                    if not filter(v):
                        self.parser.remove_option(section_name, k) 
    
    def filter_items(self, filter: callable) -> None:
        '''Applies filter() to all (key, value) pairs of the file, and only keeps values for wich it returns True'''
        for section_name, section in self.parser.items():
                for k, v in section.items():
                    if not filter(k, v):
                        self.parser.remove_option(section_name, k) 

    def save(self, path=None) -> None:
        if path == None: path = self.path
        with open(path, 'w') as f:
            self.parser.write(f)

    def delete(self, missing_ok=True) -> None:
        self.path.unlink(missing_ok=missing_ok)

class DesktopEntry(IniFile):
    '''Representation of a .desktop file, implementing both dictionary-like and specific methods and properties'''
    @staticmethod
    def new_with_defaults(path: 'str | Path') -> 'DesktopEntry':
        valid_path = DesktopEntry.validate_path(str(path))
        desktop_file = DesktopEntry(valid_path)

        desktop_file.appsection.Exec.set('')
        desktop_file.appsection.Icon.set('')
        desktop_file.appsection.Type.set('Application')
        desktop_file.appsection.Terminal.set(False)

        return desktop_file

    @staticmethod
    def validate_path(_path: (str)) -> Path:
        path = Path(_path)

        # Sets the exstension to .desktop
        if not path.suffix == '.desktop':
            path = Path(str(path) + '.desktop')
        return path


    def __init__(self, path: 'str | Path') -> None:
        super().__init__(path)

        self.writable = access(self.path, W_OK)

        if not self.path.suffix == '.desktop':
            raise ValueError(f'Path {self.path} is not a .desktop file')

    @property
    def appsection(self) -> 'AppSection': 
        return AppSection.from_parser(self.parser)
    @property
    def actionsections(self) -> dict[str, 'ActionSection']:
        return ActionSection.dict_from_parser(self.parser)

    def __lt__(self, __o: object) -> bool:
        if not self.is_loaded:
            self.load()

        if isinstance(__o, DesktopEntry):
            try:
                return self.appsection.Name.get() < __o.appsection.Name.get()
            except TypeError:
                return False
        else:
            raise TypeError(f"'<' not supported between instances of {type(self)} and {type(__o)}")